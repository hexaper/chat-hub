const peers = {};           // channel_name -> RTCPeerConnection
const userChannels = {};    // username -> channel_name
const userSeqs = {};        // username -> seq (join sequence for race detection)
const vadAnalysers = {};    // id -> { analyser, dataArray, audioCtx }
const ICE_SERVERS = { iceServers: [{ urls: 'stun:stun.l.google.com:19302' }] };
let localStream = null;
let socket = null;
let myChannel = null;
let cameraEnabled = false;  // camera starts off for remote peers
let screenSharing = false;
let screenStream = null;
let blackVideoTrack = null;
let blackCanvas = null;     // held to prevent GC killing the canvas stream
const remoteStreams = {};   // channel -> MediaStream we build ourselves
const remoteAudioElements = {}; // channel -> { element, stream }
const localMutedUsers = new Set(); // usernames muted locally (client-side only)
const pendingCandidates = {};   // channel -> RTCIceCandidateInit[]
const pendingMediaStates = {};  // channel -> { mic, cam } received before video element existed
let vadLoopId = null;

// ── Device preferences (from Settings page, stored in localStorage) ──────────
function getPreferredCamera() { return localStorage.getItem('preferredCamera') || ''; }
function getPreferredMic() { return localStorage.getItem('preferredMic') || ''; }

async function enumerateDevices() {
    const devices = await navigator.mediaDevices.enumerateDevices();
    for (const d of devices) {
        if (d.kind !== 'videoinput' && d.kind !== 'audioinput') continue;
        if (!d.deviceId) continue;
        try {
            await fetch('/devices/register/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
                body: JSON.stringify({
                    deviceId: d.deviceId,
                    label: d.label,
                    deviceType: d.kind === 'videoinput' ? 'camera' : 'microphone',
                }),
            });
        } catch (e) {
            console.warn('[Devices] Failed to register device:', d.label, e);
        }
    }
}

// ── Black video track (created once, reused) ─────────────────────────────────
function getBlackVideoTrack() {
    if (!blackVideoTrack) {
        blackCanvas = document.createElement('canvas');
        blackCanvas.width = 640;
        blackCanvas.height = 480;
        blackCanvas.getContext('2d').fillRect(0, 0, 640, 480);
        blackVideoTrack = blackCanvas.captureStream(1).getVideoTracks()[0];
    }
    return blackVideoTrack;
}

// ── Start call ──────────────────────────────────────────────────────────────
async function startCall() {
    const cameraId = getPreferredCamera();
    const micId = getPreferredMic();

    try {
        localStream = await navigator.mediaDevices.getUserMedia({
            video: cameraId ? { deviceId: { exact: cameraId } } : true,
            audio: micId ? { deviceId: { exact: micId } } : true,
        });
    } catch (e) {
        // Stored device ID no longer valid — fall back to system defaults
        if (cameraId) localStorage.removeItem('preferredCamera');
        if (micId) localStorage.removeItem('preferredMic');
        try {
            localStream = await navigator.mediaDevices.getUserMedia({ video: true, audio: true });
        } catch (e2) {
            // No media available at all — join with no local tracks so the user
            // can still see and hear other participants
            console.warn('[Media] No camera/mic available, joining without local media:', e2);
            localStream = new MediaStream();
        }
    }

    // Mic starts muted; camera preview stays live locally but peers get black track
    localStream.getAudioTracks().forEach(t => { t.enabled = false; });
    cameraEnabled = false;

    document.getElementById('localVideo').srcObject = localStream;
    updateMediaIcons('local', false, false);
    if (localStream.getAudioTracks().length > 0) startVAD('local', localStream);
    connectWebSocket(cameraId, micId);
}

document.getElementById('startBtn').addEventListener('click', startCall);

// ── Mic / camera toggle (called from icon clicks on the local tile) ───────────
function toggleMic() {
    if (!localStream) return;
    const audioTrack = localStream.getAudioTracks()[0];
    if (!audioTrack) return;
    audioTrack.enabled = !audioTrack.enabled;
    updateMediaIcons('local', audioTrack.enabled, cameraEnabled);
    broadcastMediaState();
}

async function toggleCam() {
    if (!localStream) return;
    cameraEnabled = !cameraEnabled;

    // Don't replace the track while screen sharing — camera state takes effect when share stops
    if (!screenSharing) {
        const trackToSend = cameraEnabled ? localStream.getVideoTracks()[0] : getBlackVideoTrack();
        for (const pc of Object.values(peers)) {
            const sender = pc.getSenders().find(s => s.track?.kind === 'video');
            if (sender) await sender.replaceTrack(trackToSend);
        }
    }

    updateMediaIcons('local', localStream.getAudioTracks()[0]?.enabled ?? false, cameraEnabled);
    broadcastMediaState();
}

// ── Screen share ──────────────────────────────────────────────────────────────
async function toggleScreen() {
    if (screenSharing) {
        stopScreenShare();
    } else {
        await startScreenShare();
    }
}

async function startScreenShare() {
    let stream;
    try {
        stream = await navigator.mediaDevices.getDisplayMedia({ video: true });
    } catch (e) {
        console.warn('[Screen] Could not start screen share:', e);
        return;
    }

    screenStream = stream;
    screenSharing = true;
    const screenTrack = screenStream.getVideoTracks()[0];

    // Browser's built-in "Stop sharing" button
    screenTrack.onended = () => stopScreenShare();

    // Replace video track for all current peers
    for (const pc of Object.values(peers)) {
        const sender = pc.getSenders().find(s => s.track?.kind === 'video');
        if (sender) await sender.replaceTrack(screenTrack);
    }

    // Show screen in local preview
    const localVideo = document.getElementById('localVideo');
    localVideo.srcObject = new MediaStream([screenTrack]);
    localVideo.play().catch(() => {});
    updateCamPlaceholder('local', true);   // hide the "no camera" overlay
    updateScreenIcon(true);
    broadcastMediaState();

    // Auto-spotlight local tile so the shared screen is prominent
    const localTile = document.getElementById('localVideo').closest('.video-tile');
    if (localTile && !localTile.classList.contains('spotlighted')) {
        toggleSpotlight(localTile);
    }
}

function stopScreenShare() {
    if (screenStream) {
        screenStream.getTracks().forEach(t => t.stop());
        screenStream = null;
    }
    screenSharing = false;

    // Revert local preview to camera stream
    document.getElementById('localVideo').srcObject = localStream;
    updateCamPlaceholder('local', cameraEnabled);  // restore correct overlay state

    // Revert track sent to peers
    const trackToSend = cameraEnabled ? localStream?.getVideoTracks()[0] : getBlackVideoTrack();
    for (const pc of Object.values(peers)) {
        const sender = pc.getSenders().find(s => s.track?.kind === 'video');
        if (sender && trackToSend) sender.replaceTrack(trackToSend);
    }

    updateScreenIcon(false);
    broadcastMediaState();

    // Remove spotlight if the local tile was auto-spotlighted
    const localTile = document.getElementById('localVideo').closest('.video-tile');
    if (localTile && localTile.classList.contains('spotlighted')) {
        toggleSpotlight(localTile);
    }
}

function updateScreenIcon(active) {
    const icon = document.querySelector('#media-icons-local .screen-icon i');
    if (!icon) return;
    icon.className = active ? 'bi bi-display-fill text-success' : 'bi bi-display';
}

// ── Fullscreen ────────────────────────────────────────────────────────────────
function enterFullscreen(wrapper) {
    const el = wrapper.querySelector('video') ?? wrapper;
    (el.requestFullscreen ?? el.webkitRequestFullscreen ?? el.mozRequestFullScreen)?.call(el);
}

// ── Media state icons ────────────────────────────────────────────────────────
function updateMediaIcons(id, micOn, camOn) {
    const container = document.getElementById(`media-icons-${id}`);
    if (!container) return;
    const mic = container.querySelector('.mic-icon i');
    const cam = container.querySelector('.cam-icon i');
    if (mic) mic.className = micOn ? 'bi bi-mic-fill text-success' : 'bi bi-mic-mute-fill text-danger';
    if (cam) cam.className = camOn ? 'bi bi-camera-video-fill text-success' : 'bi bi-camera-video-off-fill text-danger';
    updateCamPlaceholder(id, camOn);
}

function updateCamPlaceholder(id, camOn) {
    const el = document.getElementById(`cam-placeholder-${id}`);
    if (!el) return;
    el.style.display = camOn ? 'none' : 'flex';
}


function escapeHtml(text) {
    const d = document.createElement('div');
    d.textContent = text;
    return d.innerHTML;
}

function broadcastMediaState() {
    if (!socket || socket.readyState !== WebSocket.OPEN) return;
    const micOn = localStream?.getAudioTracks()[0]?.enabled ?? false;
    socket.send(JSON.stringify({ type: 'media_state', mic: micOn, cam: cameraEnabled || screenSharing }));
}

// ── Host controls ────────────────────────────────────────────────────────────
function hostKick(username) {
    const channel = userChannels[username];
    if (!channel || !socket) return;
    socket.send(JSON.stringify({ type: 'kick', target_channel: channel, username }));
}

function hostMute(username) {
    const channel = userChannels[username];
    if (!channel || !socket) return;
    socket.send(JSON.stringify({ type: 'mute_user', target_channel: channel }));
}

// ── Local mute (client-side only) ────────────────────────────────────────────
function localMuteToggle(username) {
    const channel = userChannels[username];
    if (localMutedUsers.has(username)) {
        localMutedUsers.delete(username);
        if (channel && remoteAudioElements[channel]) {
            remoteAudioElements[channel].element.muted = false;
        }
    } else {
        localMutedUsers.add(username);
        if (channel && remoteAudioElements[channel]) {
            remoteAudioElements[channel].element.muted = true;
        }
    }
    updateLocalMuteBtn(username);
}

function updateLocalMuteBtn(username) {
    const btn = document.getElementById(`local-mute-${username}`);
    if (!btn) return;
    const muted = localMutedUsers.has(username);
    btn.title = muted ? 'Unmute for me' : 'Mute for me';
    btn.className = muted ? 'btn btn-sm btn-warning' : 'btn btn-sm btn-outline-secondary';
    btn.querySelector('i').className = muted ? 'bi bi-volume-mute' : 'bi bi-volume-up';
}

// ── Voice activity detection ─────────────────────────────────────────────────
function startVAD(id, stream) {
    try {
        const audioCtx = new AudioContext();
        const source = audioCtx.createMediaStreamSource(stream);
        const analyser = audioCtx.createAnalyser();
        analyser.fftSize = 512;
        analyser.smoothingTimeConstant = 0.8;
        source.connect(analyser);
        vadAnalysers[id] = { analyser, dataArray: new Uint8Array(analyser.frequencyBinCount), audioCtx };
        startVadLoop();
    } catch (_) {}
}

function stopVAD(id) {
    if (vadAnalysers[id]) {
        vadAnalysers[id].audioCtx.close();
        delete vadAnalysers[id];
    }
    if (Object.keys(vadAnalysers).length === 0) stopVadLoop();
}

function vadLoop() {
    for (const [id, { analyser, dataArray }] of Object.entries(vadAnalysers)) {
        analyser.getByteFrequencyData(dataArray);
        const avg = dataArray.reduce((a, b) => a + b, 0) / dataArray.length;
        const speaking = avg > 8;
        const videoEl = id === 'local'
            ? document.getElementById('localVideo')
            : document.getElementById(`video-${id}`)?.querySelector('video');
        if (videoEl) videoEl.classList.toggle('speaking', speaking);
    }
    vadLoopId = requestAnimationFrame(vadLoop);
}

function startVadLoop() {
    if (!vadLoopId) vadLoopId = requestAnimationFrame(vadLoop);
}

function stopVadLoop() {
    if (vadLoopId) { cancelAnimationFrame(vadLoopId); vadLoopId = null; }
}

// ── Cleanup on page unload ──────────────────────────────────────────────────
function cleanupLocalResources() {
    if (screenStream) {
        screenStream.getTracks().forEach(t => t.stop());
        screenStream = null;
    }
    if (localStream) {
        localStream.getTracks().forEach(t => t.stop());
        localStream = null;
    }
    if (blackVideoTrack) {
        blackVideoTrack.stop();
        blackVideoTrack = null;
        blackCanvas = null;
    }
    for (const channel of Object.keys(peers)) {
        removePeer(channel);
    }
    if (socket && socket.readyState === WebSocket.OPEN) {
        socket.close();
    }
    for (const id of Object.keys(vadAnalysers)) {
        stopVAD(id);
    }
    stopVadLoop();
}

window.addEventListener('beforeunload', cleanupLocalResources);

// ── WebSocket / signaling ───────────────────────────────────────────────────
function connectWebSocket(cameraId, micId) {
    socket = new WebSocket(WS_URL);

    socket.onopen = () => {
        socket.send(JSON.stringify({ type: 'device_update', cameraId, microphoneId: micId }));
        broadcastMediaState();
    };

    socket.onerror = (err) => {
        console.error('[WS] WebSocket error:', err);
    };

    socket.onclose = ({ code, wasClean }) => {
        console.warn(`[WS] Connection closed (code=${code}, clean=${wasClean})`);
    };

    socket.onmessage = async ({ data }) => {
        let msg;
        try {
            msg = JSON.parse(data);
        } catch (e) {
            console.error('[WS] Received unparseable message:', data, e);
            return;
        }

        if (msg.type === 'my_channel') {
            myChannel = msg.channel;
            const loader = document.getElementById('roomLoader');
            if (loader) {
                loader.classList.add('fade-out');
                setTimeout(() => loader.remove(), 400);
            }

        } else if (msg.type === 'user_joined') {
            // If this user was previously connected with a different channel, clean up the old peer
            const oldChannel = userChannels[msg.username];
            if (oldChannel && oldChannel !== msg.channel) {
                console.log(`[WS] ${msg.username} rejoined with new channel, cleaning old peer`);
                removePeer(oldChannel);
            }
            userSeqs[msg.username] = msg.seq;
            userChannels[msg.username] = msg.channel;
            addParticipantToList(msg.username);
            if (msg.channel !== myChannel) {
                try {
                    await createOffer(msg.channel, msg.username, msg.avatar_url ?? null);
                } catch (e) {
                    console.error('[WebRTC] createOffer failed:', e);
                }
                // Re-broadcast our media state so the new joiner knows our current mic/cam status
                broadcastMediaState();
            }

        } else if (msg.type === 'user_left') {
            // Only remove if this event matches the current known session
            if (userSeqs[msg.username] !== msg.seq) {
                // Stale user_left from an old session — just clean up the old peer
                removePeer(msg.channel);
                return;
            }
            delete userSeqs[msg.username];
            delete userChannels[msg.username];
            removeParticipantFromList(msg.username);
            removePeer(msg.channel);

        } else if (msg.type === 'offer') {
            try {
                await handleOffer(msg.payload, msg.sender, msg.username, msg.avatar_url ?? null, msg.seq ?? null);
            } catch (e) {
                console.error('[WebRTC] handleOffer failed:', e);
            }
        } else if (msg.type === 'answer') {
            const pc = peers[msg.sender];
            if (pc) {
                try {
                    await pc.setRemoteDescription(msg.payload);
                    await drainCandidates(msg.sender);
                    console.log(`[WebRTC] Answer set for ${msg.username}, transceivers:`,
                        pc.getTransceivers().map(t => `${t.mid}:${t.direction}/${t.currentDirection}`));
                } catch (e) {
                    console.error('[WebRTC] setRemoteDescription(answer) failed:', e);
                }
            } else {
                console.warn('[WebRTC] No peer for answer from', msg.sender);
            }
        } else if (msg.type === 'ice-candidate') {
            const pc = peers[msg.sender];
            if (pc && pc.remoteDescription) {
                try { await pc.addIceCandidate(msg.payload); } catch (e) { console.warn('[ICE]', e); }
            } else {
                (pendingCandidates[msg.sender] ??= []).push(msg.payload);
            }

        } else if (msg.type === 'kicked') {
            socket.close();
            alert('You have been kicked from the room.');
            window.location.href = '/rooms/';

        } else if (msg.type === 'force_mute') {
            if (localStream) {
                const audioTrack = localStream.getAudioTracks()[0];
                if (audioTrack) {
                    audioTrack.enabled = false;
                    updateMediaIcons('local', false, cameraEnabled);
                    broadcastMediaState();
                }
            }

        } else if (msg.type === 'media_state' && msg.channel !== myChannel) {
            if (document.getElementById(`media-icons-${msg.channel}`)) {
                updateMediaIcons(msg.channel, msg.mic, msg.cam);
            } else {
                pendingMediaStates[msg.channel] = { mic: msg.mic, cam: msg.cam };
            }

        } else if (msg.type === 'room_closed') {
            socket.close();
            alert('The host has closed this room.');
            window.location.href = '/rooms/';
        }
    };
}

// ── ICE candidate queue ─────────────────────────────────────────────────────
async function drainCandidates(channel) {
    const queue = pendingCandidates[channel] ?? [];
    delete pendingCandidates[channel];
    for (const c of queue) {
        try { await peers[channel].addIceCandidate(c); } catch (e) { console.warn('[ICE drain]', e); }
    }
}

// ── WebRTC helpers ──────────────────────────────────────────────────────────
function setupPeerConnection(targetChannel, username, avatarUrl) {
    // Close any existing connection for this channel before creating a new one
    if (peers[targetChannel]) {
        console.warn(`[WebRTC] Replacing existing peer for channel ${targetChannel}`);
        removePeer(targetChannel);
    }

    const pc = new RTCPeerConnection(ICE_SERVERS);
    peers[targetChannel] = pc;

    pc.onicecandidate = ({ candidate }) => {
        if (candidate) {
            socket.send(JSON.stringify({ type: 'ice-candidate', target: targetChannel, payload: candidate }));
        }
    };

    pc.oniceconnectionstatechange = () => {
        const state = pc.iceConnectionState;
        console.log(`[WebRTC] ICE state for ${username}: ${state}`);
        if (state === 'connected' || state === 'completed') {
            // Broadcast our current media state now that the connection is live.
            // This is more reliable than relying on a pre-connection media_state
            // message arriving before ontrack fires.
            broadcastMediaState();
        }
        if (state === 'failed') {
            console.warn(`[WebRTC] ICE failed for ${username}, attempting restart`);
            pc.restartIce();
        }
    };

    remoteStreams[targetChannel] = new MediaStream();
    pc.ontrack = ({ track }) => {
        // Drop stale events — the connection may have been superseded by a rejoin
        if (peers[targetChannel] !== pc) return;

        console.log(`[WebRTC] ontrack: ${track.kind} from ${username} (${targetChannel})`);
        remoteStreams[targetChannel].addTrack(track);
        if (track.kind === 'video') {
            addRemoteVideo(targetChannel, username, avatarUrl, remoteStreams[targetChannel]);
        } else if (track.kind === 'audio') {
            const audioStream = new MediaStream([track]);
            const audioEl = document.createElement('audio');
            audioEl.id = `audio-${targetChannel}`;
            audioEl.srcObject = audioStream;
            audioEl.autoplay = true;
            // Apply local mute if user was muted before this audio track arrived
            if (localMutedUsers.has(username)) audioEl.muted = true;
            document.body.appendChild(audioEl);
            remoteAudioElements[targetChannel] = { element: audioEl, stream: audioStream };
            startVAD(targetChannel, audioStream);
        }
    };
    return pc;
}

function getOutboundVideoTrack() {
    if (screenSharing && screenStream) return screenStream.getVideoTracks()[0];
    return cameraEnabled ? localStream.getVideoTracks()[0] : getBlackVideoTrack();
}

function addLocalTracks(pc) {
    const audioTrack = localStream.getAudioTracks()[0];
    if (audioTrack) pc.addTrack(audioTrack, localStream);

    const videoTrack = getOutboundVideoTrack();
    if (videoTrack) pc.addTrack(videoTrack, localStream);
}

async function createOffer(targetChannel, username, avatarUrl) {
    console.log(`[WebRTC] Creating offer for ${username} (${targetChannel})`);
    const pc = setupPeerConnection(targetChannel, username, avatarUrl);
    addLocalTracks(pc);
    const offer = await pc.createOffer();
    await pc.setLocalDescription(offer);
    console.log(`[WebRTC] Offer created, sending to ${username}`);
    socket.send(JSON.stringify({ type: 'offer', target: targetChannel, payload: offer }));
}

async function handleOffer(offer, senderChannel, username, avatarUrl, seq) {
    // Populate tracking maps so cleanup works when this user refreshes or leaves
    // (they may never have sent user_joined to us if they were already in the room)
    userChannels[username] = senderChannel;
    if (seq != null) userSeqs[username] = seq;

    const pc = setupPeerConnection(senderChannel, username, avatarUrl);

    // Set remote description FIRST — this creates transceivers from the offer
    await pc.setRemoteDescription(offer);

    // Now attach our local tracks to the transceivers created by the offer
    for (const transceiver of pc.getTransceivers()) {
        const kind = transceiver.receiver.track?.kind;
        if (kind === 'audio') {
            const audioTrack = localStream.getAudioTracks()[0];
            if (audioTrack) {
                await transceiver.sender.replaceTrack(audioTrack);
                transceiver.direction = 'sendrecv';
            }
        } else if (kind === 'video') {
            const videoTrack = getOutboundVideoTrack();
            if (videoTrack) {
                await transceiver.sender.replaceTrack(videoTrack);
                transceiver.direction = 'sendrecv';
            }
        }
    }

    await drainCandidates(senderChannel);
    const answer = await pc.createAnswer();
    await pc.setLocalDescription(answer);
    console.log(`[WebRTC] Sending answer to ${username}, transceivers:`,
        pc.getTransceivers().map(t => `${t.mid}:${t.direction}/${t.currentDirection}`));
    socket.send(JSON.stringify({ type: 'answer', target: senderChannel, payload: answer }));
}

function toggleSpotlight(tile) {
    const spotlightArea = document.getElementById('spotlightArea');
    const videoGrid = document.getElementById('videoGrid');

    if (tile.classList.contains('spotlighted')) {
        // Un-spotlight: return tile to grid
        tile.classList.remove('spotlighted');
        videoGrid.appendChild(tile);
        spotlightArea.classList.add('d-none');
    } else {
        // Return any existing spotlight tile to the grid first
        const current = spotlightArea.querySelector('.video-tile');
        if (current) {
            current.classList.remove('spotlighted');
            videoGrid.appendChild(current);
        }
        // Move chosen tile into spotlight
        tile.classList.add('spotlighted');
        spotlightArea.classList.remove('d-none');
        spotlightArea.appendChild(tile);
    }
}

function buildAvatarPlaceholder(username, avatarUrl) {
    if (avatarUrl) {
        return `<img src="${escapeHtml(avatarUrl)}" alt="" style="width:80px;height:80px;border-radius:50%;object-fit:cover;opacity:0.7">`;
    }
    return `<div class="cam-placeholder-initial">${escapeHtml(username.charAt(0).toUpperCase())}</div>`;
}

function addRemoteVideo(channel, username, avatarUrl, stream) {
    if (document.getElementById(`video-${channel}`)) return;
    // If userChannels has moved on to a newer channel for this user, this call is stale
    if (userChannels[username] !== channel) return;

    const col = document.createElement('div');
    col.id = `video-${channel}`;
    col.className = 'video-tile';
    col.addEventListener('click', () => toggleSpotlight(col));

    const wrapper = document.createElement('div');
    wrapper.className = 'video-wrapper';

    const video = document.createElement('video');
    video.autoplay = true;
    video.muted = true;
    video.setAttribute('playsinline', '');
    video.className = 'w-100 rounded bg-dark';
    // Video-only stream avoids autoplay restrictions triggered by audio tracks
    video.srcObject = new MediaStream(stream.getVideoTracks());
    video.play().catch(() => {});

    const placeholder = document.createElement('div');
    placeholder.className = 'cam-placeholder';
    placeholder.id = `cam-placeholder-${channel}`;
    placeholder.innerHTML = buildAvatarPlaceholder(username, avatarUrl);

    const fsBtn = document.createElement('button');
    fsBtn.className = 'fullscreen-btn';
    fsBtn.title = 'Fullscreen';
    fsBtn.innerHTML = '<i class="bi bi-fullscreen"></i>';
    fsBtn.addEventListener('click', e => { e.stopPropagation(); enterFullscreen(wrapper); });

    const icons = document.createElement('div');
    icons.className = 'media-icons';
    icons.id = `media-icons-${channel}`;
    icons.innerHTML = `
        <span class="media-icon mic-icon"><i class="bi bi-mic-mute-fill text-danger"></i></span>
        <span class="media-icon cam-icon"><i class="bi bi-camera-video-off-fill text-danger"></i></span>`;

    wrapper.append(video, placeholder, fsBtn, icons);

    // Apply any media state that arrived before this element existed
    if (pendingMediaStates[channel]) {
        const { mic, cam } = pendingMediaStates[channel];
        delete pendingMediaStates[channel];
        updateMediaIcons(channel, mic, cam);
    }

    const label = document.createElement('p');
    label.className = 'text-center mt-1';
    const strong = document.createElement('strong');
    strong.textContent = username;  // textContent is XSS-safe
    label.appendChild(strong);

    col.append(wrapper, label);
    document.getElementById('videoGrid').appendChild(col);
}

function removePeer(channel) {
    stopVAD(channel);
    delete remoteStreams[channel];
    delete pendingCandidates[channel];
    const audioRef = remoteAudioElements[channel];
    if (audioRef) {
        audioRef.element.srcObject = null;
        audioRef.element.remove();
        delete remoteAudioElements[channel];
    }
    const pc = peers[channel];
    if (pc) { pc.close(); delete peers[channel]; }
    const tile = document.getElementById(`video-${channel}`);
    if (tile) {
        if (tile.classList.contains('spotlighted')) {
            document.getElementById('spotlightArea').classList.add('d-none');
        }
        tile.remove();
    }
}

// ── Participant list helpers ──────────────────────────────────────────────────
function addParticipantToList(username) {
    if (document.getElementById(`participant-${username}`)) return;

    const li = document.createElement('li');
    li.className = 'list-group-item d-flex justify-content-between align-items-center';
    li.id = `participant-${username}`;
    li.textContent = username;  // XSS-safe

    if (username !== USERNAME) {
        const div = document.createElement('div');
        div.className = 'd-flex gap-1';

        const localMuteBtn = document.createElement('button');
        localMuteBtn.id = `local-mute-${username}`;
        localMuteBtn.className = 'btn btn-sm btn-outline-secondary';
        localMuteBtn.title = 'Mute for me';
        localMuteBtn.innerHTML = '<i class="bi bi-volume-up"></i>';
        localMuteBtn.addEventListener('click', () => localMuteToggle(username));

        div.appendChild(localMuteBtn);

        if (IS_HOST) {
            const muteBtn = document.createElement('button');
            muteBtn.className = 'btn btn-sm btn-outline-warning';
            muteBtn.title = 'Force mute for everyone';
            muteBtn.innerHTML = '<i class="bi bi-mic-mute"></i>';
            muteBtn.addEventListener('click', () => hostMute(username));

            const kickBtn = document.createElement('button');
            kickBtn.className = 'btn btn-sm btn-outline-danger';
            kickBtn.title = 'Kick';
            kickBtn.innerHTML = '<i class="bi bi-x-lg"></i>';
            kickBtn.addEventListener('click', () => hostKick(username));

            div.append(muteBtn, kickBtn);
        }

        li.appendChild(div);
    }

    document.getElementById('participantList').appendChild(li);
}

function removeParticipantFromList(username) {
    document.getElementById(`participant-${username}`)?.remove();
}

// ── Cookie helper ─────────────────────────────────────────────────────────────
function getCookie(name) {
    return document.cookie.split(';').map(c => c.trim())
        .find(c => c.startsWith(name + '='))?.slice(name.length + 1) ?? '';
}

// Enumerate devices then auto-start the call
navigator.mediaDevices.getUserMedia({ video: true, audio: true })
    .then(() => enumerateDevices())
    .catch(() => enumerateDevices())
    .finally(() => startCall());

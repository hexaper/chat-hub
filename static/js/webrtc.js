const peers = {};           // channel_name -> RTCPeerConnection
const userChannels = {};    // username -> channel_name
const userSeqs = {};        // username -> seq (join sequence for race detection)
const vadAnalysers = {};    // id -> { analyser, dataArray, audioCtx }
const ICE_SERVERS = { iceServers: [{ urls: 'stun:stun.l.google.com:19302' }] };
let localStream = null;
let socket = null;
let myChannel = null;
let cameraEnabled = false;  // camera starts off for remote peers
let blackVideoTrack = null;
let blackCanvas = null;     // held to prevent GC killing the canvas stream
const remoteStreams = {};   // channel -> MediaStream we build ourselves
const remoteAudioElements = {}; // channel -> { element, stream }
const pendingCandidates = {};   // channel -> RTCIceCandidateInit[]
let vadLoopId = null;

// ── Device enumeration ──────────────────────────────────────────────────────
async function enumerateDevices() {
    const devices = await navigator.mediaDevices.enumerateDevices();
    const cameraSelect = document.getElementById('cameraSelect');
    const micSelect = document.getElementById('micSelect');

    devices.forEach(d => {
        const opt = new Option(d.label || `${d.kind} (${d.deviceId.slice(0, 8)})`, d.deviceId);
        if (d.kind === 'videoinput') cameraSelect.appendChild(opt);
        if (d.kind === 'audioinput') micSelect.appendChild(opt);
    });

    for (const d of devices) {
        if (d.kind !== 'videoinput' && d.kind !== 'audioinput') continue;
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
    const cameraId = document.getElementById('cameraSelect').value;
    const micId = document.getElementById('micSelect').value;

    localStream = await navigator.mediaDevices.getUserMedia({
        video: cameraId ? { deviceId: { exact: cameraId } } : true,
        audio: micId ? { deviceId: { exact: micId } } : true,
    });

    // Mic starts muted; camera preview stays live locally but peers get black track
    localStream.getAudioTracks().forEach(t => { t.enabled = false; });
    cameraEnabled = false;

    setMicBtn(false);
    setCamBtn(false);

    document.getElementById('localVideo').srcObject = localStream;
    updateMediaIcons('local', false, false);
    startVAD('local', localStream);
    connectWebSocket(cameraId, micId);
}

document.getElementById('startBtn').addEventListener('click', startCall);

// ── Mic / camera toggle ───────────────────────────────────────────────────────
function setMicBtn(enabled) {
    const btn = document.getElementById('toggleMicBtn');
    btn.textContent = enabled ? 'Mute Mic' : 'Unmute Mic';
    btn.classList.toggle('btn-outline-secondary', enabled);
    btn.classList.toggle('btn-danger', !enabled);
}

function setCamBtn(enabled) {
    const btn = document.getElementById('toggleCamBtn');
    btn.textContent = enabled ? 'Disable Camera' : 'Enable Camera';
    btn.classList.toggle('btn-outline-secondary', enabled);
    btn.classList.toggle('btn-danger', !enabled);
}

document.getElementById('toggleMicBtn').addEventListener('click', () => {
    if (!localStream) return;
    const audioTrack = localStream.getAudioTracks()[0];
    if (!audioTrack) return;
    audioTrack.enabled = !audioTrack.enabled;
    setMicBtn(audioTrack.enabled);
    updateMediaIcons('local', audioTrack.enabled, cameraEnabled);
    broadcastMediaState();
});

document.getElementById('toggleCamBtn').addEventListener('click', async () => {
    if (!localStream) return;
    cameraEnabled = !cameraEnabled;
    const videoTrack = localStream.getVideoTracks()[0];
    const trackToSend = cameraEnabled ? videoTrack : getBlackVideoTrack();

    for (const pc of Object.values(peers)) {
        const sender = pc.getSenders().find(s => s.track?.kind === 'video');
        if (sender) await sender.replaceTrack(trackToSend);
    }

    setCamBtn(cameraEnabled);
    updateMediaIcons('local', localStream.getAudioTracks()[0]?.enabled ?? false, cameraEnabled);
    broadcastMediaState();
});

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
    if (el) el.style.display = camOn ? 'none' : 'flex';
}

function broadcastMediaState() {
    if (!socket || socket.readyState !== WebSocket.OPEN) return;
    const micOn = localStream?.getAudioTracks()[0]?.enabled ?? false;
    socket.send(JSON.stringify({ type: 'media_state', mic: micOn, cam: cameraEnabled }));
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

        } else if (msg.type === 'user_joined') {
            // If this user was previously connected with a different channel, clean up the old peer
            const oldChannel = userChannels[msg.username];
            if (oldChannel && oldChannel !== msg.channel) {
                removePeer(oldChannel);
            }
            userSeqs[msg.username] = msg.seq;
            userChannels[msg.username] = msg.channel;
            addParticipantToList(msg.username);
            if (msg.channel !== myChannel) await createOffer(msg.channel, msg.username);

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
            await handleOffer(msg.payload, msg.sender, msg.username);
        } else if (msg.type === 'answer') {
            const pc = peers[msg.sender];
            if (pc) {
                await pc.setRemoteDescription(msg.payload);
                await drainCandidates(msg.sender);
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
                    setMicBtn(false);
                    updateMediaIcons('local', false, cameraEnabled);
                    broadcastMediaState();
                }
            }

        } else if (msg.type === 'media_state' && msg.channel !== myChannel) {
            updateMediaIcons(msg.channel, msg.mic, msg.cam);

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
function createPeerConnection(targetChannel, username) {
    // Close any existing connection for this channel before creating a new one
    if (peers[targetChannel]) {
        console.warn(`[WebRTC] Replacing existing peer for channel ${targetChannel}`);
        removePeer(targetChannel);
    }

    const pc = new RTCPeerConnection(ICE_SERVERS);
    peers[targetChannel] = pc;

    // Add audio and video as independent transceivers with no shared stream.
    const audioTrack = localStream.getAudioTracks()[0];
    if (audioTrack) pc.addTransceiver(audioTrack, { direction: 'sendrecv' });

    const videoTrack = cameraEnabled ? localStream.getVideoTracks()[0] : getBlackVideoTrack();
    if (videoTrack) pc.addTransceiver(videoTrack, { direction: 'sendrecv' });

    pc.onicecandidate = ({ candidate }) => {
        if (candidate) {
            socket.send(JSON.stringify({ type: 'ice-candidate', target: targetChannel, payload: candidate }));
        }
    };

    remoteStreams[targetChannel] = new MediaStream();
    pc.ontrack = ({ track }) => {
        remoteStreams[targetChannel].addTrack(track);
        if (track.kind === 'video') {
            addRemoteVideo(targetChannel, username, remoteStreams[targetChannel]);
        } else if (track.kind === 'audio') {
            const audioStream = new MediaStream([track]);
            const audioEl = document.createElement('audio');
            audioEl.id = `audio-${targetChannel}`;
            audioEl.srcObject = audioStream;
            audioEl.autoplay = true;
            document.body.appendChild(audioEl);
            remoteAudioElements[targetChannel] = { element: audioEl, stream: audioStream };
            startVAD(targetChannel, audioStream);
        }
    };
    return pc;
}

async function createOffer(targetChannel, username) {
    const pc = createPeerConnection(targetChannel, username);
    const offer = await pc.createOffer();
    await pc.setLocalDescription(offer);
    socket.send(JSON.stringify({ type: 'offer', target: targetChannel, payload: offer }));
}

async function handleOffer(offer, senderChannel, username) {
    const pc = createPeerConnection(senderChannel, username);
    await pc.setRemoteDescription(offer);
    await drainCandidates(senderChannel);
    const answer = await pc.createAnswer();
    await pc.setLocalDescription(answer);
    socket.send(JSON.stringify({ type: 'answer', target: senderChannel, payload: answer }));
}

function addRemoteVideo(channel, username, stream) {
    if (document.getElementById(`video-${channel}`)) return;

    const col = document.createElement('div');
    col.className = 'col-md-6';
    col.id = `video-${channel}`;

    const wrapper = document.createElement('div');
    wrapper.className = 'video-wrapper';

    const video = document.createElement('video');
    video.autoplay = true;
    video.muted = true;
    video.setAttribute('playsinline', '');
    video.className = 'w-100 rounded bg-dark';
    video.srcObject = stream;

    const placeholder = document.createElement('div');
    placeholder.className = 'cam-placeholder';
    placeholder.id = `cam-placeholder-${channel}`;
    placeholder.innerHTML = '<i class="bi bi-camera-video-off"></i>';

    const icons = document.createElement('div');
    icons.className = 'media-icons';
    icons.id = `media-icons-${channel}`;
    icons.innerHTML = `
        <span class="media-icon mic-icon"><i class="bi bi-mic-mute-fill text-danger"></i></span>
        <span class="media-icon cam-icon"><i class="bi bi-camera-video-off-fill text-danger"></i></span>`;

    wrapper.append(video, placeholder, icons);

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
    document.getElementById(`video-${channel}`)?.remove();
}

// ── Participant list helpers ──────────────────────────────────────────────────
function addParticipantToList(username) {
    if (document.getElementById(`participant-${username}`)) return;

    const li = document.createElement('li');
    li.className = 'list-group-item d-flex justify-content-between align-items-center';
    li.id = `participant-${username}`;
    li.textContent = username;  // XSS-safe

    if (IS_HOST && username !== USERNAME) {
        const div = document.createElement('div');

        const muteBtn = document.createElement('button');
        muteBtn.className = 'btn btn-sm btn-outline-warning me-1';
        muteBtn.textContent = 'Mute';
        muteBtn.addEventListener('click', () => hostMute(username));

        const kickBtn = document.createElement('button');
        kickBtn.className = 'btn btn-sm btn-outline-danger';
        kickBtn.textContent = 'Kick';
        kickBtn.addEventListener('click', () => hostKick(username));

        div.append(muteBtn, kickBtn);
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

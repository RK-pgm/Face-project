
(function () {
  "use strict";

  const MODEL_URL = document.body.dataset.modelUrl; 
  const MIN_FACE_RATIO = 0.22;                       

  
  function detectorOptions() {
    return new faceapi.TinyFaceDetectorOptions({ inputSize: 320, scoreThreshold: 0.5 });
  }

  function csrfToken() {
    return document.querySelector('meta[name="csrf-token"]').content;
  }

  
  async function postJson(url, data) {
    const response = await fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken() },
      body: JSON.stringify(data),
    });
    let body = null;
    try { body = await response.json(); } catch (_) {  }
    return { status: response.status, ok: response.ok, body: body };
  }

  
  
  
  
  async function loadModels() {
    if (typeof faceapi === "undefined") {
      throw new Error("FACEAPI_MISSING");
    }
    if (faceapi.tf && faceapi.tf.ready) {
      try { await faceapi.tf.ready(); } catch (_) {  }
    }
    await Promise.all([
      faceapi.nets.tinyFaceDetector.loadFromUri(MODEL_URL),
      faceapi.nets.faceLandmark68Net.loadFromUri(MODEL_URL),
      faceapi.nets.faceRecognitionNet.loadFromUri(MODEL_URL),
    ]);
  }

  
  async function startCamera(video) {
    if (!window.isSecureContext) {
      throw new Error("INSECURE_CONTEXT");
    }
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      throw new Error("NO_MEDIA_API");
    }
    const stream = await navigator.mediaDevices.getUserMedia({
      video: { width: { ideal: 640 }, height: { ideal: 480 }, facingMode: "user" },
      audio: false,
    });
    video.srcObject = stream;
    await video.play();
    if (!video.videoWidth) {
      await new Promise(function (resolve) { video.addEventListener("loadedmetadata", resolve, { once: true }); });
    }
    return stream;
  }

  function stopCamera(stream) {
    if (stream) { stream.getTracks().forEach(function (t) { t.stop(); }); }
  }

  
  function cameraErrorMessage(err) {
    const name = err && (err.name || err.message);
    switch (name) {
      case "NotAllowedError":
      case "PermissionDeniedError":
        return "Camera access was denied. Allow camera access in your browser, then refresh the page.";
      case "NotFoundError":
      case "DevicesNotFoundError":
        return "No camera found. Connect a webcam and refresh the page.";
      case "NotReadableError":
      case "TrackStartError":
        return "Could not open the camera. Close other apps using it (such as Zoom or Teams), then refresh the page.";
      case "INSECURE_CONTEXT":
        return "Camera access requires http://localhost:8000 or HTTPS. Check the page address.";
      case "NO_MEDIA_API":
        return "This browser does not support camera access. Try the latest Chrome, Edge, or Firefox.";
      case "FACEAPI_MISSING":
        return "face-api.js was not found in static/vendor/face-api. See README.md for download instructions.";
      default:
        return "Could not initialize the camera or face models: " + (name || "Unknown error") +
               " (check that all models are in static/vendor/face-api/models)";
    }
  }

  
  
  
  function setStatus(el, state, text, holdMs) {
    el.dataset.state = state;
    el.textContent = text;
    el._holdUntil = holdMs ? Date.now() + holdMs : 0;
  }

  
  function setLiveStatus(el, state, text) {
    if (el._holdUntil && Date.now() < el._holdUntil) { return; }
    setStatus(el, state, text);
  }

  
  
  function watchFaces(video, canvas, onUpdate) {
    let running = true;
    async function tick() {
      if (!running) { return; }
      try {
        if (video.readyState >= 2 && video.videoWidth) {
          const detections = await faceapi.detectAllFaces(video, detectorOptions());
          if (canvas.width !== video.videoWidth) {
            canvas.width = video.videoWidth;
            canvas.height = video.videoHeight;
          }
          const ctx = canvas.getContext("2d");
          ctx.clearRect(0, 0, canvas.width, canvas.height);
          const single = detections.length === 1;
          ctx.lineWidth = 4;
          ctx.strokeStyle = single ? "#4ade80" : "#fbbf24"; 
          detections.forEach(function (d) {
            const b = d.box;
            ctx.strokeRect(b.x, b.y, b.width, b.height);
          });
          onUpdate(detections.length, detections);
        }
      } catch (err) {
        console.error("Face detection failed", err);
      }
      setTimeout(tick, 120);
    }
    tick();
    return function stop() { running = false; };
  }

  
  
  async function extractSingleDescriptor(input, width) {
    const results = await faceapi
      .detectAllFaces(input, detectorOptions())
      .withFaceLandmarks()
      .withFaceDescriptors();
    if (results.length === 0) { return { error: "none" }; }
    if (results.length > 1) { return { error: "multiple" }; }
    if (results[0].detection.box.width < width * MIN_FACE_RATIO) { return { error: "small" }; }
    return { descriptor: Array.from(results[0].descriptor) };
  }

  function faceErrorText(code) {
    switch (code) {
      case "none": return "No face detected. Center your face and make sure there is enough light.";
      case "multiple": return "Multiple faces detected. Only one person should be in the frame.";
      case "small": return "Face is too small. Move closer to the camera.";
      default: return "Face detection failed. Please try again.";
    }
  }

  window.FaceLogin = {
    postJson: postJson,
    loadModels: loadModels,
    startCamera: startCamera,
    stopCamera: stopCamera,
    cameraErrorMessage: cameraErrorMessage,
    setStatus: setStatus,
    setLiveStatus: setLiveStatus,
    watchFaces: watchFaces,
    extractSingleDescriptor: extractSingleDescriptor,
    faceErrorText: faceErrorText,
  };
})();


(function () {
  "use strict";
  const FL = window.FaceLogin;

  const video = document.getElementById("video");
  const overlay = document.getElementById("overlay");
  const placeholder = document.getElementById("camera-placeholder");
  const statusEl = document.getElementById("face-status");
  const cameraSwitchBtn = document.getElementById("switch-camera-btn");
  const captureBtn = document.getElementById("capture-btn");
  const retakeBtn = document.getElementById("retake-btn");
  const snapshotWrap = document.getElementById("snapshot-wrap");
  const snapshotImg = document.getElementById("snapshot");
  const form = document.getElementById("register-form");
  const submitBtn = document.getElementById("submit-btn");
  const consent = document.getElementById("consent");

  let stream = null;
  let facingMode = "environment";
  let stopWatching = null;
  let liveFaceCount = 0;
  let capturing = false;
  let submitting = false;
  const captured = { descriptor: null, photo: null }; 

  function fieldError(name, text) {
    const el = document.querySelector('[data-error-for="' + name + '"]');
    if (el) { el.textContent = text || ""; }
  }

  function clearErrors() {
    document.querySelectorAll("[data-error-for]").forEach(function (el) { el.textContent = ""; });
  }

  function refreshButtons() {
    const hasPhoto = !!captured.descriptor;
    cameraSwitchBtn.disabled = !stream || capturing || submitting;
    captureBtn.disabled = !stream || hasPhoto || capturing || liveFaceCount !== 1;
    submitBtn.disabled = !(hasPhoto && consent.checked) || submitting;
  }

  
  ["pin", "pin_confirm"].forEach(function (id) {
    const el = document.getElementById(id);
    el.addEventListener("input", function () { el.value = el.value.replace(/\D/g, "").slice(0, 6); });
  });
  consent.addEventListener("change", refreshButtons);

  async function init() {
    try {
      await FL.loadModels();
      stream = await FL.startCamera(video, facingMode);
    } catch (err) {
      console.error(err);
      placeholder.textContent = "Could not open the camera";
      FL.setStatus(statusEl, "error", FL.cameraErrorMessage(err));
      return;
    }
    placeholder.hidden = true;
    startWatching();
  }

  function startWatching() {
    stopWatching = FL.watchFaces(video, overlay, function (count) {
      liveFaceCount = count;
      if (!captured.descriptor && !capturing) {
        if (count === 1) { FL.setLiveStatus(statusEl, "ok", "One face detected. You can capture a photo now."); }
        else if (count === 0) { FL.setLiveStatus(statusEl, "warn", "No face detected. Center your face and make sure there is enough light."); }
        else { FL.setLiveStatus(statusEl, "warn", "Multiple faces detected. Only one person should be in the frame."); }
      }
      refreshButtons();
    });
  }

  async function switchCamera() {
    if (!stream || capturing || submitting) { return; }
    const previousMode = facingMode;
    const nextMode = facingMode === "user" ? "environment" : "user";
    let streamStopped = false;
    try {
      const nextCamera = await FL.getAlternateCamera(stream, nextMode);
      if (stopWatching) { stopWatching(); stopWatching = null; }
      FL.stopCamera(stream);
      stream = null;
      streamStopped = true;
      video.pause();
      video.srcObject = null;
      refreshButtons();
      captured.descriptor = null;
      captured.photo = null;
      snapshotWrap.hidden = true;
      retakeBtn.hidden = true;
      await new Promise(function (resolve) { setTimeout(resolve, 300); });
      stream = await FL.startCamera(video, nextMode, true, nextCamera.deviceId);
      facingMode = nextMode;
      cameraSwitchBtn.textContent = facingMode === "user" ? "Switch to rear camera" : "Switch to front camera";
      FL.setStatus(statusEl, "idle", facingMode === "user" ? "Front camera active." : "Rear camera active.", 2500);
      startWatching();
    } catch (err) {
      console.error(err);
      FL.setStatus(statusEl, "error", FL.cameraErrorMessage(err), 5000);
      if (streamStopped) {
        try {
          stream = await FL.startCamera(video, previousMode);
          startWatching();
        } catch (restoreErr) {
          console.error(restoreErr);
        }
      }
    } finally {
      refreshButtons();
    }
  }

  cameraSwitchBtn.addEventListener("click", switchCamera);

  captureBtn.addEventListener("click", async function () {
    if (capturing || !stream) { return; }
    capturing = true;
    refreshButtons();
    FL.setStatus(statusEl, "idle", "Analyzing face…");
    try {
      
      const canvas = document.createElement("canvas");
      canvas.width = video.videoWidth;
      canvas.height = video.videoHeight;
      canvas.getContext("2d").drawImage(video, 0, 0, canvas.width, canvas.height);

      const face = await FL.extractSingleDescriptor(canvas, canvas.width);
      if (face.error) {
        
        FL.setStatus(statusEl, "warn", FL.faceErrorText(face.error), 4000);
        return;
      }
      captured.descriptor = face.descriptor;
      captured.photo = canvas.toDataURL("image/jpeg", 0.9);
      snapshotImg.src = captured.photo;
      snapshotWrap.hidden = false;
      retakeBtn.hidden = false;
      fieldError("face", "");
      FL.setStatus(statusEl, "ok", "Photo captured. One face detected. Complete the form and register.");
    } catch (err) {
      console.error(err);
      FL.setStatus(statusEl, "error", "Face analysis failed. Please try again.", 4000);
    } finally {
      capturing = false;
      refreshButtons();
    }
  });

  retakeBtn.addEventListener("click", function () {
    captured.descriptor = null;
    captured.photo = null;
    snapshotWrap.hidden = true;
    retakeBtn.hidden = true;
    FL.setStatus(statusEl, "idle", "You can take a new photo now.");
    refreshButtons();
  });

  form.addEventListener("submit", async function (event) {
    event.preventDefault();
    if (submitting || !captured.descriptor) { return; }
    clearErrors();

    const payload = {
      first_name: document.getElementById("first_name").value,
      last_name: document.getElementById("last_name").value,
      nickname: document.getElementById("nickname").value,
      pin: document.getElementById("pin").value,
      pin_confirm: document.getElementById("pin_confirm").value,
      consent: consent.checked,
      descriptor: captured.descriptor,
      photo: captured.photo,
    };

    submitting = true;
    refreshButtons();
    try {
      const res = await FL.postJson("/register/", payload);
      if (res.ok && res.body && res.body.ok) {
        FL.stopCamera(stream);
        window.location.href = res.body.redirect; 
        return;
      }
      const errors = (res.body && res.body.errors) || { __all__: "Registration failed. Please try again." };
      Object.keys(errors).forEach(function (field) { fieldError(field, errors[field]); });
    } catch (err) {
      console.error(err);
      fieldError("__all__", "Could not connect to the server. Check that the server is running.");
    } finally {
      submitting = false;
      refreshButtons();
    }
  });

  window.addEventListener("pagehide", function () {
    if (stopWatching) { stopWatching(); }
    FL.stopCamera(stream);
  });
  init();
})();

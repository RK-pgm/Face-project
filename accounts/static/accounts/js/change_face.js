
(function () {
  "use strict";
  const FL = window.FaceLogin;

  const video = document.getElementById("video");
  const overlay = document.getElementById("overlay");
  const placeholder = document.getElementById("camera-placeholder");
  const statusEl = document.getElementById("face-status");
  const captureBtn = document.getElementById("capture-btn");
  const retakeBtn = document.getElementById("retake-btn");
  const snapshotWrap = document.getElementById("snapshot-wrap");
  const snapshotImg = document.getElementById("snapshot");
  const form = document.getElementById("change-face-form");
  const submitBtn = document.getElementById("submit-btn");
  const pinInput = document.getElementById("pin");

  let stream = null;
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
    captureBtn.disabled = !stream || hasPhoto || capturing || liveFaceCount !== 1;
    submitBtn.disabled = !hasPhoto || submitting;
  }

  pinInput.addEventListener("input", function () {
    pinInput.value = pinInput.value.replace(/\D/g, "").slice(0, 6);
  });

  async function init() {
    try {
      await FL.loadModels();
      stream = await FL.startCamera(video);
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
        if (count === 1) { FL.setLiveStatus(statusEl, "ok", "One face detected. You can capture a new photo now."); }
        else if (count === 0) { FL.setLiveStatus(statusEl, "warn", "No face detected. Center your face and make sure there is enough light."); }
        else { FL.setLiveStatus(statusEl, "warn", "Multiple faces detected. Only one person should be in the frame."); }
      }
      refreshButtons();
    });
  }

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
      FL.setStatus(statusEl, "ok", "Photo captured. One face detected. Enter your PIN and save.");
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
      pin: pinInput.value,
      descriptor: captured.descriptor,
      photo: captured.photo,
    };

    submitting = true;
    refreshButtons();
    try {
      const res = await FL.postJson("/me/change-face/", payload);
      if (res.ok && res.body && res.body.ok) {
        FL.stopCamera(stream);
        window.location.href = res.body.redirect;
        return;
      }
      if (res.status === 429 && res.body) {
        fieldError("__all__", res.body.message);
      } else {
        const errors = (res.body && res.body.errors) || { __all__: "Could not update your face photo. Please try again." };
        Object.keys(errors).forEach(function (field) { fieldError(field, errors[field]); });
      }
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


(function () {
  "use strict";
  const FL = window.FaceLogin;

  const video = document.getElementById("video");
  const overlay = document.getElementById("overlay");
  const placeholder = document.getElementById("camera-placeholder");
  const statusEl = document.getElementById("face-status");
  const form = document.getElementById("login-form");
  const nameInput = document.getElementById("name");
  const pinInput = document.getElementById("pin");
  const submitBtn = document.getElementById("submit-btn");
  const resultBox = document.getElementById("result");

  let stream = null;
  let ready = false;   
  let busy = false;    

  function showResult(text) {
    resultBox.textContent = text;
    resultBox.hidden = !text;
  }

  function refreshButton() {
    submitBtn.disabled = !ready || busy;
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
    ready = true;
    refreshButton();

    FL.watchFaces(video, overlay, function (count) {
      if (busy) { return; }
      if (count === 1) { FL.setLiveStatus(statusEl, "ok", "Face detected. Ready to scan."); }
      else if (count === 0) { FL.setLiveStatus(statusEl, "warn", "No face detected. Center your face in the frame."); }
      else { FL.setLiveStatus(statusEl, "warn", "Multiple faces detected. Only one person should be in the frame."); }
    });
  }

  form.addEventListener("submit", async function (event) {
    event.preventDefault();
    if (!ready || busy) { return; }
    showResult("");

    const name = nameInput.value.trim();
    const pin = pinInput.value;
    if (!name || !/^\d{4,6}$/.test(pin)) {
      showResult("Enter your name and a 4–6 digit PIN.");
      return;
    }

    busy = true;
    refreshButton();
    FL.setStatus(statusEl, "idle", "Scanning face…");

    try {
      const face = await FL.extractSingleDescriptor(video, video.videoWidth);
      if (face.error) {
        
        FL.setStatus(statusEl, "warn", FL.faceErrorText(face.error), 4000);
        return;
      }

      const res = await FL.postJson("/login/", { name: name, pin: pin, descriptor: face.descriptor });
      if (res.ok && res.body && res.body.ok) {
        FL.stopCamera(stream);
        FL.setStatus(statusEl, "ok", "Sign-in successful. Redirecting to your dashboard…");
        window.location.href = res.body.redirect;
        return;
      }
      showResult((res.body && res.body.message) || "Sign-in failed. Please try again.");
      pinInput.value = "";
      pinInput.focus();
    } catch (err) {
      console.error(err);
      showResult("Could not connect to the server. Check that the server is running.");
    } finally {
      busy = false;
      refreshButton();
    }
  });

  window.addEventListener("pagehide", function () { FL.stopCamera(stream); });
  init();
})();

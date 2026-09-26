/*
 * หน้าสมัครสมาชิก
 * ขั้นตอน: เปิดกล้อง → ถ่ายรูป (ต้องเจอใบหน้าเดียว) → ได้ descriptor + รูป → กรอกฟอร์ม → ส่ง JSON ไป Django
 * รูปที่ส่งไปเก็บ และ descriptor มาจากเฟรมเดียวกัน (canvas ใบเดียวกัน) เพื่อให้ตรงกัน
 */
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
  const form = document.getElementById("register-form");
  const submitBtn = document.getElementById("submit-btn");
  const consent = document.getElementById("consent");

  let stream = null;
  let stopWatching = null;
  let liveFaceCount = 0;
  let capturing = false;
  let submitting = false;
  const captured = { descriptor: null, photo: null }; // ผลการถ่าย (ยังไม่ส่งไปไหนจนกว่าจะกดสมัคร)

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
    submitBtn.disabled = !(hasPhoto && consent.checked) || submitting;
  }

  // PIN รับเฉพาะตัวเลข
  ["pin", "pin_confirm"].forEach(function (id) {
    const el = document.getElementById(id);
    el.addEventListener("input", function () { el.value = el.value.replace(/\D/g, "").slice(0, 6); });
  });
  consent.addEventListener("change", refreshButtons);

  async function init() {
    try {
      await FL.loadModels();
      stream = await FL.startCamera(video);
    } catch (err) {
      console.error(err);
      placeholder.textContent = "เปิดกล้องไม่ได้";
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
        if (count === 1) { FL.setLiveStatus(statusEl, "ok", "พบใบหน้า 1 ใบหน้า — กด \"ถ่ายรูปหน้า\" ได้เลย"); }
        else if (count === 0) { FL.setLiveStatus(statusEl, "warn", "ไม่พบใบหน้า — ให้ใบหน้าอยู่กลางกรอบและมีแสงสว่างพอ"); }
        else { FL.setLiveStatus(statusEl, "warn", "พบหลายใบหน้า — ให้เหลือเพียงคนเดียว"); }
      }
      refreshButtons();
    });
  }

  captureBtn.addEventListener("click", async function () {
    if (capturing || !stream) { return; }
    capturing = true;
    refreshButtons();
    FL.setStatus(statusEl, "idle", "กำลังวิเคราะห์ใบหน้า…");
    try {
      // จับภาพเฟรมปัจจุบันลง canvas แล้วสกัด descriptor จาก canvas นั้น
      const canvas = document.createElement("canvas");
      canvas.width = video.videoWidth;
      canvas.height = video.videoHeight;
      canvas.getContext("2d").drawImage(video, 0, 0, canvas.width, canvas.height);

      const face = await FL.extractSingleDescriptor(canvas, canvas.width);
      if (face.error) {
        // ต้องเจอใบหน้าเดียวเท่านั้น ไม่งั้นไม่ให้ผ่านขั้นนี้
        FL.setStatus(statusEl, "warn", FL.faceErrorText(face.error), 4000);
        return;
      }
      captured.descriptor = face.descriptor;
      captured.photo = canvas.toDataURL("image/jpeg", 0.9);
      snapshotImg.src = captured.photo;
      snapshotWrap.hidden = false;
      retakeBtn.hidden = false;
      fieldError("face", "");
      FL.setStatus(statusEl, "ok", "ถ่ายรูปสำเร็จ (ตรวจพบใบหน้าเดียว) — กรอกข้อมูลแล้วกดสมัครได้เลย");
    } catch (err) {
      console.error(err);
      FL.setStatus(statusEl, "error", "วิเคราะห์ใบหน้าไม่สำเร็จ ลองถ่ายอีกครั้ง", 4000);
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
    FL.setStatus(statusEl, "idle", "ถ่ายรูปใหม่ได้เลย");
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
        window.location.href = res.body.redirect; // ไปหน้าล็อกอิน (จะมีข้อความแจ้งรหัสสมาชิก)
        return;
      }
      const errors = (res.body && res.body.errors) || { __all__: "สมัครไม่สำเร็จ กรุณาลองใหม่" };
      Object.keys(errors).forEach(function (field) { fieldError(field, errors[field]); });
    } catch (err) {
      console.error(err);
      fieldError("__all__", "เชื่อมต่อเซิร์ฟเวอร์ไม่ได้ ตรวจสอบว่า runserver ยังทำงานอยู่");
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

/*
 * หน้าล็อกอิน: กรอกชื่อ + PIN แล้วสแกนหน้า
 * เบราว์เซอร์สกัด descriptor จากวิดีโอ ณ วินาทีที่กดปุ่ม แล้วส่ง {name, pin, descriptor} ไปให้ Django ตัดสิน
 * (ตัวตัดสินผ่าน/ไม่ผ่านอยู่ที่เซิร์ฟเวอร์ ไม่ใช่ในเบราว์เซอร์)
 */
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
  let ready = false;   // โมเดลและกล้องพร้อมแล้ว
  let busy = false;    // กำลังส่งข้อมูล

  function showResult(text) {
    resultBox.textContent = text;
    resultBox.hidden = !text;
  }

  function refreshButton() {
    submitBtn.disabled = !ready || busy;
  }

  // PIN รับเฉพาะตัวเลข
  pinInput.addEventListener("input", function () {
    pinInput.value = pinInput.value.replace(/\D/g, "").slice(0, 6);
  });

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
    ready = true;
    refreshButton();

    FL.watchFaces(video, overlay, function (count) {
      if (busy) { return; }
      if (count === 1) { FL.setLiveStatus(statusEl, "ok", "พบใบหน้า พร้อมสแกน"); }
      else if (count === 0) { FL.setLiveStatus(statusEl, "warn", "ไม่พบใบหน้า — ให้ใบหน้าอยู่กลางกรอบ"); }
      else { FL.setLiveStatus(statusEl, "warn", "พบหลายใบหน้า — ให้เหลือเพียงคนเดียว"); }
    });
  }

  form.addEventListener("submit", async function (event) {
    event.preventDefault();
    if (!ready || busy) { return; }
    showResult("");

    const name = nameInput.value.trim();
    const pin = pinInput.value;
    if (!name || !/^\d{4,6}$/.test(pin)) {
      showResult("กรุณากรอกชื่อและรหัสตัวเลข 4-6 หลักให้ครบ");
      return;
    }

    busy = true;
    refreshButton();
    FL.setStatus(statusEl, "idle", "กำลังสแกนใบหน้า…");

    try {
      const face = await FL.extractSingleDescriptor(video, video.videoWidth);
      if (face.error) {
        // ไม่เจอหน้าเดียวที่ชัดเจน → เตือนและ "ไม่ส่งข้อมูล" ไปเซิร์ฟเวอร์
        FL.setStatus(statusEl, "warn", FL.faceErrorText(face.error), 4000);
        return;
      }

      const res = await FL.postJson("/login/", { name: name, pin: pin, descriptor: face.descriptor });
      if (res.ok && res.body && res.body.ok) {
        FL.stopCamera(stream);
        FL.setStatus(statusEl, "ok", "เข้าสู่ระบบสำเร็จ กำลังพาไปหน้าของคุณ…");
        window.location.href = res.body.redirect;
        return;
      }
      showResult((res.body && res.body.message) || "เข้าสู่ระบบไม่สำเร็จ กรุณาลองใหม่");
      pinInput.value = "";
      pinInput.focus();
    } catch (err) {
      console.error(err);
      showResult("เชื่อมต่อเซิร์ฟเวอร์ไม่ได้ ตรวจสอบว่า runserver ยังทำงานอยู่");
    } finally {
      busy = false;
      refreshButton();
    }
  });

  window.addEventListener("pagehide", function () { FL.stopCamera(stream); });
  init();
})();

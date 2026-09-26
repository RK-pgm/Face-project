/*
 * ฟังก์ชันกลางที่ใช้ทั้งหน้าสมัครและหน้าล็อกอิน
 * ทั้งหมดรันในเบราว์เซอร์ — ภาพจากกล้อง "ไม่ถูกส่งไปตรวจที่ไหน" ระหว่างที่ยังไม่กดปุ่ม
 * สิ่งที่ส่งไปเซิร์ฟเวอร์มีแค่ descriptor (ตัวเลข 128 ค่า) และตอนสมัครจะมีรูปถ่าย 1 รูป
 *
 * ต้องโหลด face-api.js (ตัวแปร faceapi) ก่อนไฟล์นี้
 */
(function () {
  "use strict";

  const MODEL_URL = document.body.dataset.modelUrl; // เช่น /static/vendor/face-api/models
  const MIN_FACE_RATIO = 0.22;                       // ใบหน้าต้องกว้างอย่างน้อย 22% ของภาพ (ไม่ไกลเกินไป)

  // TinyFaceDetector: ตัวตรวจจับใบหน้าแบบเล็กและเร็ว เหมาะกับการรันสดในเบราว์เซอร์
  function detectorOptions() {
    return new faceapi.TinyFaceDetectorOptions({ inputSize: 320, scoreThreshold: 0.5 });
  }

  function csrfToken() {
    return document.querySelector('meta[name="csrf-token"]').content;
  }

  // ส่ง JSON ไปที่ Django พร้อม CSRF token (Django จะปฏิเสธคำขอ POST ที่ไม่มี token นี้)
  async function postJson(url, data) {
    const response = await fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken() },
      body: JSON.stringify(data),
    });
    let body = null;
    try { body = await response.json(); } catch (_) { /* เซิร์ฟเวอร์ตอบมาไม่ใช่ JSON */ }
    return { status: response.status, ok: response.ok, body: body };
  }

  // โหลดโมเดล 3 ตัวจากโฟลเดอร์ static (ไม่ต้องใช้อินเทอร์เน็ต)
  //   tinyFaceDetector  = หาตำแหน่งใบหน้า
  //   faceLandmark68Net = หาจุดสำคัญ 68 จุดบนใบหน้า (ตา จมูก ปาก) ใช้จัดใบหน้าให้ตรงก่อนสกัดค่า
  //   faceRecognitionNet= สกัด descriptor 128 ค่า
  async function loadModels() {
    if (typeof faceapi === "undefined") {
      throw new Error("FACEAPI_MISSING");
    }
    if (faceapi.tf && faceapi.tf.ready) {
      try { await faceapi.tf.ready(); } catch (_) { /* ใช้ backend สำรองต่อไป */ }
    }
    await Promise.all([
      faceapi.nets.tinyFaceDetector.loadFromUri(MODEL_URL),
      faceapi.nets.faceLandmark68Net.loadFromUri(MODEL_URL),
      faceapi.nets.faceRecognitionNet.loadFromUri(MODEL_URL),
    ]);
  }

  // เปิดกล้อง (เบราว์เซอร์อนุญาตเฉพาะ localhost หรือ HTTPS)
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

  // แปลง error ของกล้องเป็นข้อความภาษาไทยที่แก้ปัญหาต่อได้
  function cameraErrorMessage(err) {
    const name = err && (err.name || err.message);
    switch (name) {
      case "NotAllowedError":
      case "PermissionDeniedError":
        return "ไม่ได้รับอนุญาตให้ใช้กล้อง — กดไอคอนกล้อง/แม่กุญแจข้างช่องที่อยู่เว็บ แล้วเลือก \"อนุญาต\" จากนั้นรีเฟรชหน้า";
      case "NotFoundError":
      case "DevicesNotFoundError":
        return "ไม่พบกล้องในเครื่องนี้ กรุณาต่อกล้องเว็บแคมแล้วรีเฟรชหน้า";
      case "NotReadableError":
      case "TrackStartError":
        return "เปิดกล้องไม่ได้ อาจมีโปรแกรมอื่นใช้กล้องอยู่ (เช่น Zoom, Teams) ให้ปิดโปรแกรมนั้นแล้วรีเฟรชหน้า";
      case "INSECURE_CONTEXT":
        return "เบราว์เซอร์เปิดกล้องได้เฉพาะเมื่อเข้าผ่าน http://localhost:8000 หรือ HTTPS — ตรวจสอบที่อยู่เว็บอีกครั้ง";
      case "NO_MEDIA_API":
        return "เบราว์เซอร์นี้ไม่รองรับการใช้กล้อง ลองใช้ Chrome, Edge หรือ Firefox เวอร์ชันล่าสุด";
      case "FACEAPI_MISSING":
        return "ไม่พบไฟล์ face-api.js ในโฟลเดอร์ static/vendor/face-api — ดูวิธีดาวน์โหลดใน README.md";
      default:
        return "เตรียมกล้องหรือโมเดลไม่สำเร็จ: " + (name || "ไม่ทราบสาเหตุ") +
               " (ตรวจว่าไฟล์โมเดลอยู่ครบใน static/vendor/face-api/models)";
    }
  }

  // ตั้งข้อความสถานะใต้กล้อง state = idle | ok | warn | error
  // holdMs (ไม่บังคับ): "ตรึง" ข้อความไว้กี่มิลลิวินาที ไม่ให้ข้อความสถานะสดจากกล้องมาเขียนทับ
  // (ใช้กับข้อความเตือนตอนถ่าย/สแกนไม่ผ่าน ไม่งั้นผู้ใช้จะเห็นข้อความเตือนแค่แวบเดียว)
  function setStatus(el, state, text, holdMs) {
    el.dataset.state = state;
    el.textContent = text;
    el._holdUntil = holdMs ? Date.now() + holdMs : 0;
  }

  // ข้อความสถานะ "สด" จากการตรวจใบหน้าต่อเนื่อง — ถ้ามีข้อความที่ตรึงไว้อยู่ จะไม่เขียนทับ
  function setLiveStatus(el, state, text) {
    if (el._holdUntil && Date.now() < el._holdUntil) { return; }
    setStatus(el, state, text);
  }

  // ตรวจใบหน้าจากวิดีโอต่อเนื่อง วาดกรอบทับบน canvas และแจ้งจำนวนใบหน้าที่เจอ
  // คืนฟังก์ชัน stop() สำหรับหยุด
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
          ctx.strokeStyle = single ? "#4ade80" : "#fbbf24"; // เขียว = เจอหน้าเดียว, เหลือง = ไม่เจอ/หลายหน้า
          detections.forEach(function (d) {
            const b = d.box;
            ctx.strokeRect(b.x, b.y, b.width, b.height);
          });
          onUpdate(detections.length, detections);
        }
      } catch (err) {
        console.error("ตรวจใบหน้าไม่สำเร็จ", err);
      }
      setTimeout(tick, 120);
    }
    tick();
    return function stop() { running = false; };
  }

  // สกัด descriptor จากภาพ (video หรือ canvas) — ต้องเจอใบหน้า "เดียว" เท่านั้น
  // คืน { descriptor: [128 ค่า] } หรือ { error: "none" | "multiple" | "small" }
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
      case "none": return "ไม่พบใบหน้า — ให้ใบหน้าอยู่กลางกรอบและมีแสงสว่างพอ";
      case "multiple": return "พบหลายใบหน้าในภาพ — ให้เหลือเพียงคนเดียว";
      case "small": return "ใบหน้าเล็กเกินไป — ขยับเข้าใกล้กล้องอีกนิด";
      default: return "ตรวจใบหน้าไม่สำเร็จ ลองอีกครั้ง";
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

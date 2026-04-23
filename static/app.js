function formatDuration(seconds) {
  if (!seconds && seconds !== 0) return "";
  const sec = Number(seconds);
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = Math.floor(sec % 60);

  if (h > 0) {
    return `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  }
  return `${m}:${String(s).padStart(2, "0")}`;
}

document.addEventListener("DOMContentLoaded", () => {
  const urlInput = document.getElementById("urlInput");
  const previewBtn = document.getElementById("previewBtn");
  const saveBtn = document.getElementById("saveBtn");
  const statusBox = document.getElementById("statusText");
  const previewCard = document.getElementById("previewCard");
  const previewImage = document.getElementById("previewImage");
  const previewTitle = document.getElementById("previewTitle");
  const previewMeta = document.getElementById("previewMeta");
  const progressWrap = document.getElementById("progressWrap");
  const progressBar = document.getElementById("progressBar");

  function setStatus(message) {
    if (statusBox) statusBox.textContent = message || "";
  }

  function showProgress(percent) {
    if (!progressWrap || !progressBar) return;
    progressWrap.style.display = "block";
    progressBar.style.width = `${percent || 0}%`;
  }

  function hideProgress() {
    if (!progressWrap || !progressBar) return;
    progressWrap.style.display = "none";
    progressBar.style.width = "0%";
  }

  async function analyzeUrl() {
    const url = (urlInput?.value || "").trim();

    if (!url) {
      setStatus("Önce link yapıştır.");
      return;
    }

    previewBtn.disabled = true;
    previewBtn.textContent = "Önizleme hazırlanıyor...";
    setStatus("Link analiz ediliyor...");
    hideProgress();

    try {
      const response = await fetch("/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url })
      });
      const data = await response.json();

      if (!response.ok || !data.success) {
        throw new Error(data.error || "Önizleme alınamadı.");
      }

      if (previewCard) {
        previewCard.style.display = "block";
      }
      if (previewImage) previewImage.src = data.thumbnail || "";
      if (previewTitle) previewTitle.textContent = data.title || "Video hazır";

      const metaParts = [];
      if (data.platform) metaParts.push(data.platform);
      if (data.duration || data.duration === 0) metaParts.push(formatDuration(data.duration));
      if (data.uploader) metaParts.push(data.uploader);

      if (previewMeta) previewMeta.innerHTML = metaParts.map(item => `<span>${item}</span>`).join("");

      setStatus("Önizleme hazır.");
    } catch (error) {
      setStatus(error.message || "Önizleme alınamadı.");
      if (previewCard) previewCard.style.display = "none";
    } finally {
      previewBtn.disabled = false;
      previewBtn.textContent = "Önizle";
    }
  }

  async function startSave() {
    const url = (urlInput?.value || "").trim();

    if (!url) {
      setStatus("Önce link yapıştır.");
      return;
    }

    saveBtn.disabled = true;
    saveBtn.textContent = "Hazırlanıyor...";
    setStatus("Kaydetme görevi başlatılıyor...");
    showProgress(4);

    try {
      const response = await fetch("/download", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url })
      });
      const data = await response.json();

      if (!response.ok || !data.success) {
        throw new Error(data.error || "Kaydetme başlatılamadı.");
      }

      pollStatus(data.job_id);
    } catch (error) {
      saveBtn.disabled = false;
      saveBtn.textContent = "Kaydet";
      setStatus(error.message || "Kaydetme başlatılamadı.");
      hideProgress();
    }
  }

  async function pollStatus(jobId) {
    try {
      const response = await fetch(`/status/${jobId}`);
      const data = await response.json();

      if (!response.ok || !data.success) {
        throw new Error(data.error || "Durum alınamadı.");
      }

      const status = data.status || "";
      const percent = Number(data.percent || 0);
      showProgress(percent);

      if (status === "queued" || status === "starting") {
        setStatus("Hazırlanıyor...");
      } else if (status === "downloading") {
        setStatus(`Kaydediliyor... %${percent}`);
      } else if (status === "processing") {
        setStatus("Dosya hazırlanıyor...");
      } else if (status === "done") {
        setStatus("Hazır. Dosya indiriliyor...");
        showProgress(100);
        window.location.href = `/file/${jobId}`;
        saveBtn.disabled = false;
        saveBtn.textContent = "Kaydet";
        setTimeout(() => hideProgress(), 2000);
        return;
      } else if (status === "error") {
        throw new Error(data.error || "Kaydetme sırasında hata oluştu.");
      }

      setTimeout(() => pollStatus(jobId), 1200);
    } catch (error) {
      saveBtn.disabled = false;
      saveBtn.textContent = "Kaydet";
      setStatus(error.message || "Kaydetme sırasında hata oluştu.");
      hideProgress();
    }
  }

  if (previewBtn) previewBtn.addEventListener("click", analyzeUrl);
  if (saveBtn) saveBtn.addEventListener("click", startSave);

  if (urlInput) {
    urlInput.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        analyzeUrl();
      }
    });
  }
});

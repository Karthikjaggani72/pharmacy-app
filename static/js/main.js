
document.addEventListener("DOMContentLoaded", function () {
  const qty = document.querySelector("input[name='qty']");
  const mrp = document.querySelector("input[name='mrp']");
  const total = document.querySelector("input[name='total']");
  const discount = document.querySelector("input[name='discount']");
  const net = document.querySelector("input[name='net']");

  function updateNet() {
    const q = parseFloat(qty?.value || 0);
    const m = parseFloat(mrp?.value || 0);
    const d = parseFloat(discount?.value || 0);
    const t = q * m;
    const n = t - (t * d / 100);
    if (total) total.value = t.toFixed(2);
    if (net) net.value = n.toFixed(2);
  }

  [qty, mrp, discount].forEach(el => {
    el?.addEventListener("input", updateNet);
  });
});

/* AI Shopping web prototype — guest basket (localStorage) + optimizer relay.
 *
 * The browser performs NO money math: every total, subtotal, pack count and
 * coverage number is rendered verbatim from the server response of
 * POST /basket/optimize (which relays the backend's deterministic optimizer).
 */
(function () {
  "use strict";

  var STORAGE_KEY = "aiBasket.v1";
  var MAX_ITEMS = 50;

  var labelsEl = document.getElementById("basket-labels");
  var labels = {};
  try { labels = JSON.parse(labelsEl.textContent); } catch (e) { labels = {}; }

  var root = document.getElementById("basket-root");
  var resultsEl = document.getElementById("optimize-results");
  var optimizeBtn = document.getElementById("basket-optimize");
  var clearBtn = document.getElementById("basket-clear");
  var countEl = document.getElementById("basket-count");

  function load() {
    try {
      var raw = window.localStorage.getItem(STORAGE_KEY);
      var parsed = raw ? JSON.parse(raw) : [];
      return Array.isArray(parsed) ? parsed : [];
    } catch (e) { return []; }
  }

  function save(items) {
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(items.slice(0, MAX_ITEMS)));
    } catch (e) { /* storage unavailable */ }
  }

  function itemKey(it) {
    return (it.canonicalId ? "c" + it.canonicalId : "r" + it.retailerId);
  }

  function labelFor(it) { return it.label || "Производ"; }

  /* ---- formatting: mirrors web/app/formatting.py (Macedonian) ---- */
  function groupDigits(digits) {
    var out = "";
    for (var i = 0; i < digits.length; i++) {
      if (i > 0 && (digits.length - i) % 3 === 0) out += ".";
      out += digits[i];
    }
    return out;
  }
  function formatNumber(value, decimals) {
    var fixed = Number(value).toFixed(decimals === undefined ? 2 : decimals);
    var negative = fixed.charAt(0) === "-";
    var unsigned = negative ? fixed.substring(1) : fixed;
    var parts = unsigned.split(".");
    var grouped = groupDigits(parts[0]);
    var body = parts.length > 1 ? grouped + "," + parts[1] : grouped;
    return negative ? "-" + body : body;
  }
  function formatMkd(value) { return formatNumber(value, 2) + " ден."; }
  function formatQuantity(value) {
    var n = Number(value);
    if (Number.isInteger(n)) return formatNumber(n, 0);
    return formatNumber(n, 3).replace(/0+$/, "").replace(/\.$/, "");
  }
  function formatDate(iso) {
    if (!iso) return "–";
    var d = new Date(iso);
    if (isNaN(d.getTime())) return "–";
    var p = function (x) { return (x < 10 ? "0" : "") + x; };
    return p(d.getDate()) + "." + p(d.getMonth() + 1) + "." + d.getFullYear();
  }

  /* ---- basket UI ---- */
  function updateCount(items) {
    if (!countEl) return;
    if (items.length > 0) {
      countEl.textContent = String(items.length);
      countEl.hidden = false;
    } else {
      countEl.hidden = true;
    }
  }

  function render() {
    var items = load();
    updateCount(items);
    if (!root) return;
    root.textContent = "";
    items.forEach(function (item, index) {
      var row = document.createElement("div");
      row.className = "basket-row";

      var name = document.createElement("div");
      var label = document.createElement("span");
      label.className = "label";
      label.textContent = labelFor(item);
      name.appendChild(label);
      if (item.size) {
        var size = document.createElement("span");
        size.className = "size-label";
        size.textContent = " · " + item.size;
        name.appendChild(size);
      }
      row.appendChild(name);

      var qtyLabel = document.createElement("label");
      qtyLabel.className = "sr-only";
      qtyLabel.setAttribute("for", "qty-" + index);
      qtyLabel.textContent = labels.quantity || "Количина";
      row.appendChild(qtyLabel);
      var qty = document.createElement("input");
      qty.type = "number";
      qty.id = "qty-" + index;
      qty.min = "0";
      qty.step = "any";
      qty.value = String(item.quantity);
      qty.addEventListener("change", function () {
        var v = parseFloat(qty.value);
        item.quantity = isNaN(v) || v < 0 ? 0 : v;
        save(load().map(function (it) { return itemKey(it) === itemKey(item) ? item : it; }));
      });
      row.appendChild(qty);

      var unitLabel = document.createElement("label");
      unitLabel.className = "sr-only";
      unitLabel.setAttribute("for", "unit-" + index);
      unitLabel.textContent = labels.unit || "Единица";
      row.appendChild(unitLabel);
      var unit = document.createElement("select");
      unit.id = "unit-" + index;
      (labels.units || []).forEach(function (u) {
        var opt = document.createElement("option");
        opt.value = u;
        opt.textContent = u;
        if (item.unit === u) opt.selected = true;
        unit.appendChild(opt);
      });
      unit.addEventListener("change", function () {
        item.unit = unit.value;
        save(load().map(function (it) { return itemKey(it) === itemKey(item) ? item : it; }));
      });
      row.appendChild(unit);

      var rm = document.createElement("button");
      rm.type = "button";
      rm.className = "secondary";
      rm.textContent = labels.remove || "Отстрани";
      rm.addEventListener("click", function () {
        save(load().filter(function (it) { return itemKey(it) !== itemKey(item); }));
        render();
      });
      row.appendChild(rm);

      root.appendChild(row);
    });
  }

  function bindAddButtons() {
    var buttons = document.querySelectorAll(".btn-add");
    Array.prototype.forEach.call(buttons, function (btn) {
      btn.addEventListener("click", function () {
        var items = load();
        var candidate = {
          canonicalId: btn.dataset.canonicalId ? parseInt(btn.dataset.canonicalId, 10) : null,
          retailerId: parseInt(btn.dataset.retailerProductId, 10),
          label: btn.dataset.label || "",
          size: btn.dataset.size || "",
          retailer: btn.dataset.retailer || "",
          quantity: 1,
          unit: "pack"
        };
        var key = itemKey(candidate);
        var existing = items.filter(function (it) { return itemKey(it) === key; })[0];
        if (existing) {
          existing.quantity = Number(existing.quantity) + 1;
        } else {
          if (items.length >= MAX_ITEMS) return;
          items.push(candidate);
        }
        save(items);
        updateCount(items);
        if (root) { render(); }
        btn.textContent = "Додадено ✓";
        window.setTimeout(function () { btn.textContent = "Додај во кошничка"; }, 1200);
      });
    });
  }

  /* ---- optimization ---- */
  function lineTotal(line) { return line.lineTotalMkd; }

  function renderMissing(missing, container) {
    if (!missing || missing.length === 0) return;
    var head = document.createElement("p");
    head.className = "missing";
    head.textContent = (labels.missing || "Недостасува") + ": " + missing.length;
    container.appendChild(head);
    var ul = document.createElement("ul");
    missing.forEach(function (m) {
      var li = document.createElement("li");
      var reason = (labels.missing_reasons || {})[m.reason] || m.reason;
      li.textContent = (m.requestedName || "?") + " (" + formatQuantity(m.requestedQuantity) + " " +
        (m.requestedUnit || "") + ") — " + reason;
      ul.appendChild(li);
    });
    container.appendChild(ul);
  }

  function storeCard(title, store) {
    var card = document.createElement("section");
    card.className = "result-card";
    var h = document.createElement("h2");
    h.textContent = title;
    card.appendChild(h);

    var meta = document.createElement("p");
    meta.textContent = store.storeName + " (" + (store.retailerName || "") +
      (store.city ? " · " + store.city : "") + ")";
    card.appendChild(meta);

    var cov = document.createElement("p");
    cov.textContent = (labels.coverage || "Покритие") + ": " + store.itemsCovered + "/" +
      store.totalItemsRequested + " · " + formatQuantity(Number(store.coverageRatio) * 100) + "%";
    card.appendChild(cov);

    var total = document.createElement("p");
    total.className = "total-line";
    total.textContent = (labels.total || "Вкупно") + ": " + formatMkd(store.totalMkd);
    card.appendChild(total);

    if (Number(store.savingsVsHighestCoveredSingleStoreMkd) > 0) {
      var sav = document.createElement("p");
      sav.className = "savings";
      sav.textContent = "Заштеда најмногу " + formatMkd(store.savingsVsHighestCoveredSingleStoreMkd) +
        " во однос на најскапа продавница со исто покритие";
      card.appendChild(sav);
    }

    var table = document.createElement("table");
    var tbody = document.createElement("tbody");
    (store.coveredItems || []).forEach(function (line) {
      var tr = document.createElement("tr");
      var td1 = document.createElement("td");
      td1.textContent = (line.matchedListingName || line.requestedName || "") +
        (line.isSubstitute ? " — " + (labels.substitute || "Замена") : "");
      var td2 = document.createElement("td");
      td2.textContent = "×" + formatQuantity(line.packsNeeded);
      var td3 = document.createElement("td");
      td3.className = "store-total";
      td3.textContent = formatMkd(lineTotal(line));
      tr.appendChild(td1); tr.appendChild(td2); tr.appendChild(td3);
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    card.appendChild(table);

    renderMissing(store.missingItems, card);
    return card;
  }

  function renderMultiPlan(plan) {
    var card = document.createElement("section");
    card.className = "result-card";
    var h = document.createElement("h2");
    h.textContent = labels.multi_plan || "Најдобра поделба меѓу продавници";
    card.appendChild(h);

    var allocs = plan.storeAllocations || [];
    if (allocs.length === 0 || plan.itemsCovered === 0) {
      var none = document.createElement("p");
      none.className = "muted";
      none.textContent = (labels.recommendations || {})[plan.recommendationReason] || plan.recommendationReason || "–";
      card.appendChild(none);
      renderMissing(plan.missingItems, card);
      return card;
    }

    var table = document.createElement("table");
    var tbody = document.createElement("tbody");
    allocs.forEach(function (a) {
      var tr = document.createElement("tr");
      var td1 = document.createElement("td");
      td1.textContent = a.storeName + " (" + (a.retailerName || "") + ")";
      var td2 = document.createElement("td");
      td2.className = "store-total";
      td2.textContent = formatMkd(a.subtotalMkd);
      tr.appendChild(td1); tr.appendChild(td2);
      tbody.appendChild(tr);
    });
    var trTotal = document.createElement("tr");
    var tdL = document.createElement("td");
    tdL.textContent = labels.total || "Вкупно";
    var tdR = document.createElement("td");
    tdR.className = "total-line";
    tdR.textContent = formatMkd(plan.totalMkd);
    trTotal.appendChild(tdL); trTotal.appendChild(tdR);
    tbody.appendChild(trTotal);
    table.appendChild(tbody);
    card.appendChild(table);

    if (Number(plan.savingsVsBestSingleStoreMkd) > 0) {
      var sav = document.createElement("p");
      sav.className = "savings";
      sav.textContent = (labels.savings_vs_single || "Заштеда") + ": " +
        formatMkd(plan.savingsVsBestSingleStoreMkd) + " — " +
        (plan.meetsMinSavingsThreshold ? (labels.meets_threshold || "") : (labels.below_threshold || ""));
      card.appendChild(sav);
    } else {
      var why = document.createElement("p");
      why.className = "muted";
      why.textContent = (labels.recommendations || {})[plan.recommendationReason] || plan.recommendationReason || "";
      card.appendChild(why);
    }

    renderMissing(plan.missingItems, card);
    return card;
  }

  function renderRankings(rankings) {
    if (!rankings || rankings.length === 0) return null;
    var card = document.createElement("section");
    card.className = "result-card";
    var h = document.createElement("h2");
    h.textContent = labels.rankings || "Продавници";
    card.appendChild(h);
    var table = document.createElement("table");
    var tbody = document.createElement("tbody");
    rankings.slice(0, 5).forEach(function (s) {
      var tr = document.createElement("tr");
      var td1 = document.createElement("td");
      td1.textContent = s.storeName + " (" + (s.retailerName || "") + ")";
      var td2 = document.createElement("td");
      td2.textContent = s.itemsCovered + "/" + s.totalItemsRequested;
      var td3 = document.createElement("td");
      td3.className = "store-total";
      td3.textContent = s.itemsCovered === 0 ? "\u2013" : formatMkd(s.totalMkd);
      tr.appendChild(td1); tr.appendChild(td2); tr.appendChild(td3);
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    card.appendChild(table);
    return card;
  }

  function optimize() {
    var items = load();
    if (!resultsEl) return;
    resultsEl.textContent = "";
    if (items.length === 0) {
      var p = document.createElement("p");
      p.className = "api-error";
      p.textContent = labels.no_items || "Додајте барем една ставка.";
      resultsEl.appendChild(p);
      return;
    }

    optimizeBtn.disabled = true;
    var payload = {
      items: items.map(function (it) {
        var entry = { quantity: it.quantity, unit: it.unit, itemLabel: it.label };
        if (it.canonicalId) entry.canonicalProductId = it.canonicalId;
        else entry.retailerProductId = it.retailerId;
        return entry;
      }),
      maxStores: 2,
      allowSubstitutes: false,
      inStockOnly: true
    };

    window.fetch("/basket/optimize", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    }).then(function (res) {
      return res.json().then(function (body) { return { status: res.status, body: body }; });
    }).then(function (r) {
      optimizeBtn.disabled = false;
      if (r.status !== 200) {
        var err = document.createElement("p");
        err.className = "api-error";
        err.textContent = (labels.error_prefix || "Грешка") +
          (r.body && r.body.error ? " (" + r.body.error + ")" : "");
        resultsEl.appendChild(err);
        return;
      }
      var data = r.body;
      if (data.bestSingleStore) {
        resultsEl.appendChild(storeCard(labels.best_single || "Најдобра продавница", data.bestSingleStore));
      }
      if (data.bestMultiStorePlan) {
        resultsEl.appendChild(renderMultiPlan(data.bestMultiStorePlan));
      }
      var rk = renderRankings(data.singleStoreRankings);
      if (rk) { resultsEl.appendChild(rk); }
    }).catch(function () {
      optimizeBtn.disabled = false;
      var err = document.createElement("p");
      err.className = "api-error";
      err.textContent = labels.error_prefix || "Грешка";
      resultsEl.appendChild(err);
    });
  }

  if (optimizeBtn) optimizeBtn.addEventListener("click", optimize);
  if (clearBtn) {
    clearBtn.addEventListener("click", function () {
      save([]);
      render();
      if (resultsEl) resultsEl.textContent = "";
    });
  }

  render();
  bindAddButtons();
})();

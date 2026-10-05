(() => {
  "use strict";

  const app = document.getElementById("pos-app");
  if (!app) return;

  const byId = (id) => document.getElementById(id);
  const csrfToken = app.querySelector("[name=csrfmiddlewaretoken]")?.value || "";
  const state = {
    register: null,
    session: null,
    registers: [],
    means: [],
    paymentMethods: [],
    series: [],
    priceLists: [],
    categories: [],
    productCategories: [],
    units: [],
    taxRates: { "10": 18, "20": 0, "30": 0, "40": 0 },
    catalogProducts: [],
    catalogRequest: 0,
    productSearchMode: app.dataset.productSearchMode === "CATALOG" ? "CATALOG" : "SEARCH",
    selectedPriceList: null,
    selectedCategory: "",
    permissions: new Set(),
    cart: new Map(),
    payments: [],
    selectedCustomer: null,
    documentType: "NV",
    paymentCondition: "CASH",
    currency: "PEN",
    productResults: [],
    activeProductIndex: -1,
    customerResults: [],
    activeCustomerIndex: -1,
    invoiceableTickets: [],
    paymentSequence: 0,
    idempotencyKey: null,
    draftTransactionId: null,
    activeCartLineId: null,
    globalDiscount: 0,
    cashSummary: null,
    suggestedOpeningTotals: { PEN: "0.00", USD: "0.00" },
    creditCollections: [],
    currentReceipt: null,
    returnIdempotencyKey: null,
    debitNoteIdempotencyKey: null,
    autoDraftLoaded: false,
    memoLineId: null,
    busy: false,
  };

  const cashDenominations = [200, 100, 50, 20, 10, 5, 2, 1, 0.5, 0.2, 0.1];

  const endpoints = {
    bootstrap: app.dataset.bootstrapUrl,
    products: app.dataset.productsUrl,
    productCreate: app.dataset.productCreateUrl,
    productCommercial: app.dataset.productCommercialUrl,
    customers: app.dataset.customersUrl,
    open: app.dataset.openUrl,
    checkout: app.dataset.checkoutUrl,
    draft: app.dataset.draftUrl,
    invoiceable: app.dataset.invoiceableUrl,
    invoiceRequest: app.dataset.invoiceRequestUrl,
    consolidate: app.dataset.consolidateUrl,
    recentSales: app.dataset.recentSalesUrl,
    collections: app.dataset.collectionsUrl,
    config: app.dataset.configUrl,
  };

  const currencySymbol = (currency = state.currency) => CurrencyDisplay.symbol(currency);
  const number = (value) => {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : 0;
  };
  const fixed = (value, digits = 2) => number(value).toFixed(digits);
  const roundMoney = (value) => Math.round((number(value) + Number.EPSILON) * 100) / 100;
  const escapeHtml = (value) => String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
  const localDate = () => {
    const date = new Date();
    date.setMinutes(date.getMinutes() - date.getTimezoneOffset());
    return date.toISOString().slice(0, 10);
  };
  const uuid = () => (
    globalThis.crypto?.randomUUID?.()
    || "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (char) => {
      const random = Math.random() * 16 | 0;
      return (char === "x" ? random : (random & 0x3 | 0x8)).toString(16);
    })
  );

  function hasPermission(code) {
    return state.permissions.has(code);
  }

  function markSaleDirty() {
    if (!state.draftTransactionId) state.idempotencyKey = null;
  }

  function errorMessage(payload, fallback = "No se pudo completar la operación.") {
    if (!payload) return fallback;
    if (typeof payload === "string") return payload;
    if (Array.isArray(payload)) return payload.map((item) => errorMessage(item, "")).filter(Boolean).join(" ");
    if (payload.detail) return errorMessage(payload.detail, fallback);
    const messages = Object.entries(payload)
      .filter(([key]) => key !== "code")
      .flatMap(([key, value]) => {
        const detail = errorMessage(value, "");
        return detail ? `${key}: ${detail}` : [];
      });
    return messages.join(" ") || fallback;
  }

  async function api(url, options = {}) {
    const headers = { Accept: "application/json", ...(options.headers || {}) };
    if (options.body && !(options.body instanceof FormData)) {
      headers["Content-Type"] = "application/json";
    }
    if ((options.method || "GET").toUpperCase() !== "GET") {
      headers["X-CSRFToken"] = csrfToken;
    }
    const response = await fetch(url, {
      credentials: "same-origin",
      ...options,
      headers,
    });
    let payload = null;
    try {
      payload = await response.json();
    } catch (_error) {
      payload = null;
    }
    if (!response.ok) {
      const error = new Error(errorMessage(payload));
      error.status = response.status;
      error.payload = payload;
      throw error;
    }
    return payload;
  }

  function showAlert(message, kind = "error") {
    const alert = byId("pos-alert");
    byId("pos-alert-message").textContent = message;
    alert.classList.toggle("is-success", kind === "success");
    alert.hidden = false;
    byId("pos-live-region").textContent = message;
  }

  function hideAlert() {
    byId("pos-alert").hidden = true;
  }

  function setBusy(value, label = "Procesando…") {
    state.busy = value;
    byId("pos-loading-text").textContent = label;
    byId("pos-loading").hidden = !value;
    if (byId("confirm-checkout-button")) byId("confirm-checkout-button").disabled = value;
    updateCheckoutAvailability();
  }

  function openDialog(dialog) {
    if (dialog && !dialog.open) dialog.showModal();
  }

  function closeDialog(dialog) {
    if (dialog?.open) dialog.close();
  }

  function renderDenominations(containerId) {
    const container = byId(containerId);
    const symbol = containerId === "opening-denominations"
      ? currencySymbol(byId("opening-currency")?.value)
      : currencySymbol();
    container.innerHTML = cashDenominations.map((denomination) => `
      <label>
        <span class="fw-bold">${symbol} ${fixed(denomination)}</span>
        <input type="number" min="0" step="1" value="0" inputmode="numeric" data-denomination="${denomination}">
      </label>`).join("");
  }

  function collectDenominations(containerId) {
    return [...byId(containerId).querySelectorAll("[data-denomination]")]
      .map((input) => ({
        denomination: fixed(input.dataset.denomination),
        quantity: Math.max(parseInt(input.value || "0", 10) || 0, 0),
      }))
      .filter((item) => item.quantity > 0);
  }

  function denominationTotal(containerId) {
    return collectDenominations(containerId).reduce(
      (total, item) => total + number(item.denomination) * item.quantity,
      0,
    );
  }

  function updateCashDifferencePreview() {
    if (!state.cashSummary) return;
    const difference = roundMoney(
      number(byId("counted-cash").value) - number(state.cashSummary.expected_cash_total),
    );
    const preview = byId("cash-difference-preview");
    preview.textContent = `Diferencia estimada: ${currencySymbol()} ${fixed(difference)}`;
    preview.classList.toggle("is-difference", difference !== 0);
    const tenderDifference = [...byId("close-tender-counts").querySelectorAll("[data-tender-id]")]
      .some((input) => roundMoney(number(input.value) - number(input.dataset.expectedAmount)) !== 0);
    const requiresReason = difference !== 0 || tenderDifference;
    byId("closing-note").required = requiresReason;
    byId("closing-note-hint").textContent = requiresReason ? "(obligatoria por diferencia)" : "(opcional)";
  }

  function updateCashAllocation(autoFillSafe = false) {
    const counted = number(byId("counted-cash").value);
    const drawer = number(byId("next-opening-total").value);
    const bank = number(byId("bank-deposit-total").value);
    if (autoFillSafe) byId("safe-deposit-total").value = fixed(Math.max(counted - drawer - bank, 0));
    const safe = number(byId("safe-deposit-total").value);
    const difference = roundMoney(counted - drawer - safe - bank);
    const preview = byId("cash-allocation-preview");
    preview.textContent = difference === 0
      ? `Distribución completa: gaveta ${currencySymbol()} ${fixed(drawer)} · caja fuerte ${currencySymbol()} ${fixed(safe)} · banco ${currencySymbol()} ${fixed(bank)}`
      : `Falta distribuir ${currencySymbol()} ${fixed(difference)}`;
    preview.classList.toggle("is-difference", difference !== 0);
    const showBank = bank > 0;
    byId("bank-deposit-destination").hidden = !showBank;
    byId("bank-deposit-destination-label").hidden = !showBank;
    byId("bank-deposit-destination").required = showBank;
    byId("close-session-submit").disabled = !state.cashSummary?.can_close || difference !== 0;
  }

  function updateCashMovementPermissions() {
    const canAuthorize = hasPermission("authorize.pos.cash_movement");
    document.querySelectorAll("[data-requires-movement-authorization]").forEach((option) => {
      option.disabled = !canAuthorize;
    });
    if (byId("movement-type").selectedOptions[0]?.disabled) byId("movement-type").value = "PAY_IN";
  }

  function selectedSeries(type = state.documentType) {
    return state.series.filter((item) => item.document_type === type);
  }

  function populateSeries() {
    const select = byId("document-series");
    const series = selectedSeries();
    select.innerHTML = series.length
      ? series.map((item) => `<option value="${item.id}">${escapeHtml(item.series)} · N.º ${item.next_number}</option>`).join("")
      : '<option value="">Sin serie configurada</option>';
    byId("invoice-series").innerHTML = selectedSeries("01").length
      ? selectedSeries("01").map((item) => `<option value="${item.id}">${escapeHtml(item.series)} · N.º ${item.next_number}</option>`).join("")
      : '<option value="">Sin serie de factura</option>';
    updateCheckoutAvailability();
  }

  function setDocumentType(type) {
    if (["01", "03"].includes(type) && !hasPermission("issue.pos.invoice")) {
      showAlert("No tiene permiso para emitir comprobantes desde el POS.");
      return;
    }
    state.documentType = type;
    markSaleDirty();
    document.querySelectorAll("[data-document-type]").forEach((button) => {
      button.classList.toggle("active", button.dataset.documentType === type);
      button.setAttribute("aria-pressed", button.dataset.documentType === type ? "true" : "false");
    });
    populateSeries();
    updateCheckoutAvailability();
  }

  function defaultDueDate() {
    const date = new Date();
    const method = state.paymentMethods.find((item) => item.id === byId("payment-method")?.value);
    date.setDate(date.getDate() + Math.max(number(method?.credit_days ?? 0), 0));
    date.setMinutes(date.getMinutes() - date.getTimezoneOffset());
    return date.toISOString().slice(0, 10);
  }

  function populatePaymentMethods() {
    const isCash = state.paymentCondition === "CASH";
    const methods = state.paymentMethods.filter((item) => Boolean(item.is_credit) !== isCash);
    const select = byId("payment-method");
    select.innerHTML = methods.length
      ? methods.map((item) => `<option value="${item.id}">${escapeHtml(item.name)}</option>`).join("")
      : `<option value="">${isCash ? "Contado" : "Sin condición de crédito configurada"}</option>`;
  }

  function setPaymentCondition(condition) {
    if (condition === "CREDIT" && !hasPermission("sell.pos.credit")) {
      showAlert("No tiene permiso para registrar ventas a crédito.");
      return;
    }
    state.paymentCondition = condition;
    markSaleDirty();
    document.querySelectorAll("[data-payment-condition]").forEach((button) => {
      button.classList.toggle("active", button.dataset.paymentCondition === condition);
      button.setAttribute("aria-pressed", button.dataset.paymentCondition === condition ? "true" : "false");
    });
    const isCredit = condition === "CREDIT";
    byId("credit-due-wrap").hidden = !isCredit;
    byId("credit-due-date").required = isCredit;
    byId("credit-due-date").min = localDate();
    if (isCredit && !byId("credit-due-date").value) {
      byId("credit-due-date").value = defaultDueDate();
    }
    byId("payments-title").textContent = isCredit ? "Adelanto (opcional)" : "Pagos";
    byId("checkout-button").querySelector("span").textContent = isCredit
      ? "Registrar venta a crédito"
      : "Guardar y cobrar";
    populatePaymentMethods();
    if (isCredit) {
      state.payments = [];
      renderPayments();
    } else {
      ensureDefaultPayment(true);
    }
    updateCheckoutAvailability();
  }

  function setSessionState() {
    const pill = byId("session-state");
    pill.classList.remove("is-loading", "is-closed");
    if (state.session) {
      pill.querySelector("span:last-child").textContent = `Caja abierta · ${state.session.register_code}`;
    } else {
      pill.classList.add("is-closed");
      pill.querySelector("span:last-child").textContent = "Caja cerrada";
    }
    byId("open-movement").disabled = !state.session || !hasPermission("manage.pos.cash_movements");
    byId("open-close-session").disabled = !state.session || !hasPermission("close.pos.cash");
    byId("open-consolidation").disabled = !state.session || !hasPermission("consolidate.pos.invoice");
    byId("open-reprints").disabled = !hasPermission("reprint.pos.receipt");
    byId("quick-cash-movement").disabled = !state.session || !hasPermission("manage.pos.cash_movements");
    byId("quick-close-session").disabled = !state.session || !hasPermission("close.pos.cash");
    byId("quick-sales-history").disabled = !hasPermission("reprint.pos.receipt");
    byId("sale-currency").disabled = Boolean(state.session);
    byId("open-collections").disabled = !state.session || !hasPermission("manage.pos.collections");
    byId("quick-collections").disabled = !state.session || !hasPermission("manage.pos.collections");
  }

  function useDefaultCustomer() {
    if (!state.register?.default_customer) {
      selectCustomer(null);
      return;
    }
    selectCustomer({
      id: state.register.default_customer,
      legal_name: state.register.default_customer_name || "Cliente predeterminado",
      document_number: state.register.default_customer_document_number || "",
      address: state.register.default_customer_address || "",
      document_type: "",
    });
  }

  async function loadBootstrap(registerId = null) {
    setBusy(true, "Preparando punto de venta…");
    hideAlert();
    try {
      const query = registerId ? `?register_id=${encodeURIComponent(registerId)}` : "";
      const data = await api(`${endpoints.bootstrap}${query}`);
      state.registers = data.registers || [];
      state.means = data.means_of_payment || [];
      state.paymentMethods = data.payment_methods || [];
      state.series = data.document_series || [];
      state.priceLists = data.price_lists || [];
      state.categories = data.categories || [];
      state.productCategories = data.product_categories || [];
      state.units = data.units || [];
      state.taxRates = data.tax_rates || state.taxRates;
      state.permissions = new Set(data.permissions || []);
      state.suggestedOpeningTotals = data.suggested_opening_totals || { PEN: "0.00", USD: "0.00" };
      updateCashMovementPermissions();
      byId("global-discount").disabled = !hasPermission("apply.pos.discount");
      byId("global-discount-row").title = hasPermission("apply.pos.discount") ? "" : "Sin permiso para aplicar descuentos";
      if (state.productSearchMode === "CATALOG") renderCategoryFilters();

      const registerSelect = byId("pos-register");
      registerSelect.innerHTML = state.registers.length
        ? state.registers.map((item) => `<option value="${item.id}">${escapeHtml(item.code)} · ${escapeHtml(item.name)}</option>`).join("")
        : '<option value="">No hay cajas configuradas</option>';

      if (!state.registers.length) {
        state.register = null;
        state.session = null;
        setSessionState();
        showAlert("No existe una caja POS activa para esta sucursal. Configure una caja antes de vender.");
        const readiness = byId("pos-readiness");
        readiness.hidden = false;
        byId("pos-readiness-message").textContent = "No hay una caja POS activa. Cree una configuración para habilitar búsqueda, ventas y apertura de caja.";
        return;
      }

      if (!data.selected_register) {
        const saved = localStorage.getItem("apudig.pos.register");
        const preferred = state.registers.find((item) => item.id === saved) || state.registers[0];
        await loadBootstrap(preferred.id);
        return;
      }

      state.register = data.selected_register;
      state.session = data.open_session;
      if (state.session) {
        state.currency = state.session.currency;
        byId("sale-currency").value = state.currency;
        byId("sale-currency").disabled = true;
        byId("exchange-rate-wrap").hidden = state.currency === "PEN";
        renderCart();
      } else {
        byId("sale-currency").disabled = false;
      }
      byId("pos-readiness").hidden = true;
      registerSelect.value = state.register.id;
      localStorage.setItem("apudig.pos.register", state.register.id);
      setSessionState();
      populatePriceLists();
      setDocumentType(state.register.default_document_type_code || "NV");
      document.querySelector('[data-payment-condition="CREDIT"]').disabled = !hasPermission("sell.pos.credit");
      setPaymentCondition("CASH");
      useDefaultCustomer();
      if (state.productSearchMode === "CATALOG") await loadCatalog();
      if (!state.session) {
        if (hasPermission("open.pos.cash")) {
          byId("opening-total").value = fixed(state.suggestedOpeningTotals[byId("opening-currency").value] || 0);
          openDialog(byId("open-session-dialog"));
          setTimeout(() => byId("opening-total").focus(), 50);
        } else {
          showAlert("Esta caja no tiene una sesión abierta y su usuario no puede abrirla.");
        }
      } else if (!state.autoDraftLoaded) {
        const requestedDraft = new URLSearchParams(window.location.search).get("draft");
        state.autoDraftLoaded = true;
        if (requestedDraft) await loadDraft(requestedDraft);
      }
      setTimeout(() => byId("product-search").focus(), 80);
    } catch (error) {
      showAlert(error.message);
    } finally {
      setBusy(false);
    }
  }

  function lineTotals(line) {
    const grossBeforeDiscount = line.netPrice * line.quantity;
    const discount = Math.min(Math.max(line.discount, 0), grossBeforeDiscount);
    const rawNet = Math.max(grossBeforeDiscount - discount, 0);
    const net = roundMoney(rawNet);
    const tax = line.taxType === "10" ? roundMoney(rawNet * (line.igvRate / 100)) : 0;
    return { net, tax, discount: roundMoney(discount), total: net + tax };
  }

  function totals() {
    const result = [...state.cart.values()].reduce((acc, line) => {
      const values = lineTotals(line);
      acc.subtotal += values.net;
      acc.tax += values.tax;
      acc.discount += values.discount;
      acc.total += values.total;
      acc.quantity += line.quantity;
      acc.lines.push({ line, ...values });
      return acc;
    }, { subtotal: 0, tax: 0, discount: 0, total: 0, quantity: 0, lines: [] });
    const globalDiscount = Math.min(Math.max(number(state.globalDiscount), 0), result.subtotal);
    if (globalDiscount > 0 && result.subtotal > 0) {
      let remainingDiscount = globalDiscount;
      let remainingBase = result.subtotal;
      result.lines.filter((item) => item.line.taxType !== "11" && item.net > 0).forEach((item, index, eligible) => {
        const part = index === eligible.length - 1
          ? remainingDiscount
          : Math.min(roundMoney(remainingDiscount * item.net / remainingBase), remainingDiscount);
        if (item.line.taxType === "10") {
          result.tax += roundMoney((item.net - part) * item.line.igvRate / 100) - item.tax;
        }
        remainingDiscount -= part;
        remainingBase -= item.net;
      });
      result.subtotal -= globalDiscount;
      result.total = result.subtotal + result.tax;
      result.discount += globalDiscount;
    }
    result.globalDiscount = globalDiscount;
    result.subtotal = roundMoney(result.subtotal);
    result.tax = roundMoney(result.tax);
    result.discount = roundMoney(result.discount);
    result.total = roundMoney(result.total);
    return result;
  }

  function grossUnitPrice(line) {
    return line.taxType === "10" ? line.netPrice * (1 + line.igvRate / 100) : line.netPrice;
  }

  function addProduct(product) {
    if (product.unit_price === null) {
      showAlert(`No hay precio configurado en ${currencySymbol()} para ${product.name}.`);
      return;
    }
    const existing = state.cart.get(product.id);
    if (existing) {
      existing.quantity += 1;
    } else {
      const units = product.units?.length ? product.units : [{
        id: product.unit_id,
        code: product.unit,
        conversion_factor: "1",
        unit_price: product.unit_price,
        is_default_sale: true,
      }];
      const selectedUnit = units.find((item) => item.id === product.unit_id) || units[0];
      const conversionFactor = Math.max(number(selectedUnit.conversion_factor), 0.000001);
      state.cart.set(product.id, {
        id: product.id,
        sku: product.sku,
        name: product.name,
        unitId: selectedUnit.id,
        unit: selectedUnit.code,
        units,
        conversionFactor,
        netPrice: number(selectedUnit.unit_price),
        originalNetPrice: number(selectedUnit.unit_price),
        priceChanged: false,
        quantity: 1,
        discount: 0,
        memo: "",
        taxType: product.tax_type || "10",
        igvRate: number(product.igv_rate || 0),
        baseStock: number(product.stock),
        stock: number(product.stock) / conversionFactor,
        stockUnit: product.stock_unit || product.unit,
        tracksInventory: Boolean(product.tracks_inventory),
      });
    }
    state.activeCartLineId = product.id;
    markSaleDirty();
    byId("product-search").value = "";
    hideProductResults();
    renderCart();
    if (state.productSearchMode === "CATALOG") loadCatalog("");
    // On iOS, returning focus to a small search field keeps the software
    // keyboard open and Safari's automatic zoom after choosing a product.
    // Desktop scanners/keyboard workflows retain the convenient refocus.
    if (window.matchMedia("(min-width: 821px)").matches) {
      byId("product-search").focus();
    } else {
      document.activeElement?.blur();
      requestAnimationFrame(() => window.scrollTo(0, window.scrollY));
    }
  }

  function renderCart() {
    const lines = [...state.cart.values()];
    byId("cart-empty").hidden = lines.length > 0;
    byId("cart-table-wrap").hidden = lines.length === 0;
    byId("clear-cart").disabled = lines.length === 0;
    const quantity = totals().quantity;
    byId("cart-count").textContent = `${fixed(quantity, quantity % 1 ? 3 : 0)} ${lines.length === 1 ? "artículo" : "artículos"}`;
    byId("cart-lines").innerHTML = lines.map((line) => {
      const values = lineTotals(line);
      const canChangePrice = line.manual || hasPermission("change.pos.price");
      const canDiscount = hasPermission("apply.pos.discount");
      const unitControl = line.units.length > 1
        ? `<select class="pos-unit-select" data-action="unit" aria-label="Unidad de ${escapeHtml(line.name)}">
            ${line.units.map((unit) => `<option value="${unit.id}" ${unit.id === line.unitId ? "selected" : ""} ${unit.unit_price === null ? "disabled" : ""}>${escapeHtml(unit.code)}</option>`).join("")}
          </select>`
        : `<span>${escapeHtml(line.unit)}</span>`;
      const productControl = line.manual
        ? `<div class="pos-manual-product-fields">
            <input class="pos-manual-description" data-action="description" type="text" maxlength="500" value="${escapeHtml(line.name)}" placeholder="Descripción del producto o servicio" aria-label="Descripción de la línea libre">
            <input class="pos-manual-code" data-action="code" type="text" maxlength="100" value="${escapeHtml(line.sku)}" placeholder="SIN CÓDIGO" aria-label="Código de la línea libre">
          </div>`
        : `<span class="pos-product-name">${escapeHtml(line.name)}</span>`;
      const taxControl = line.manual
        ? `<select class="pos-manual-tax" data-action="tax" aria-label="Impuesto de ${escapeHtml(line.name)}">
            <option value="10" ${line.taxType === "10" ? "selected" : ""}>IGV ${fixed(state.taxRates["10"] || 18, 0)}%</option>
            <option value="20" ${line.taxType === "20" ? "selected" : ""}>Exonerado</option>
            <option value="30" ${line.taxType === "30" ? "selected" : ""}>Inafecto</option>
            <option value="40" ${line.taxType === "40" ? "selected" : ""}>Exportación</option>
          </select>`
        : `<span class="pos-tax-label">${line.taxType === "10" ? `IGV ${fixed(line.igvRate, 0)}%` : "Sin IGV"}</span>`;
      return `
        <tr data-line-id="${line.id}" class="${state.activeCartLineId === line.id ? "is-selected" : ""}">
          <td>
            ${productControl}
            <span class="pos-product-meta">${escapeHtml(line.sku)} · ${unitControl} · ${line.manual ? '<b class="pos-manual-badge">Línea libre · Sin stock</b>' : `Stock ${fixed(line.stock, 3)} ${escapeHtml(line.unit)}`}</span>
            ${canDiscount ? `<label class="pos-line-discount">Desc. neto <span class="currency-label">${currencySymbol()}</span><input class="pos-discount-input" data-action="discount" type="number" min="0" step="0.01" value="${fixed(line.discount)}" aria-label="Descuento de ${escapeHtml(line.name)}"></label>` : ""}
            ${line.memo ? `<span class="pos-line-memo"><i class="ti ti-notes"></i>${escapeHtml(line.memo)}</span>` : ""}
          </td>
          <td>
            <div class="pos-quantity">
              <button type="button" data-action="decrease" aria-label="Reducir cantidad">−</button>
              <input data-action="quantity" type="number" min="0.001" step="0.001" inputmode="decimal" value="${fixed(line.quantity, line.quantity % 1 ? 3 : 0)}" aria-label="Cantidad de ${escapeHtml(line.name)}">
              <button type="button" data-action="increase" aria-label="Aumentar cantidad">+</button>
            </div>
          </td>
          <td><input class="pos-price-input" data-action="price" type="number" min="0" step="0.01" inputmode="decimal" value="${fixed(grossUnitPrice(line))}" ${canChangePrice ? "" : "disabled"} aria-label="Precio unitario de ${escapeHtml(line.name)}"></td>
          <td>${taxControl}</td>
          <td class="text-end"><span class="pos-line-total">${currencySymbol()} ${fixed(values.total)}</span></td>
          <td><div class="pos-line-actions">${line.manual ? "" : `<button class="pos-line-info" data-action="prices" type="button" aria-label="Ver listas de precios de ${escapeHtml(line.name)}" title="Listas de precios"><i class="ti ti-tags"></i></button><button class="pos-line-info" data-action="stock" type="button" aria-label="Ver stock por almacén de ${escapeHtml(line.name)}" title="Stock por almacén"><i class="ti ti-building-warehouse"></i></button>`}<button class="pos-memo-line ${line.memo ? "has-value" : ""}" data-action="memo" type="button" aria-label="Información adicional de ${escapeHtml(line.name)}" title="Información adicional"><i class="ti ti-notes"></i></button><button class="pos-remove-line" data-action="remove" type="button" aria-label="Quitar ${escapeHtml(line.name)}"><i class="ti ti-trash"></i></button></div></td>
        </tr>`;
    }).join("");
    updateTotals();
  }

  function updateTotals() {
    const values = totals();
    document.querySelectorAll(".currency-label").forEach((element) => { element.textContent = currencySymbol(); });
    byId("subtotal").textContent = fixed(values.subtotal);
    byId("discount-total").textContent = fixed(values.discount);
    byId("global-discount").value = fixed(state.globalDiscount);
    byId("igv-total").textContent = fixed(values.tax);
    byId("sale-total").textContent = fixed(values.total);
    byId("checkout-total").textContent = fixed(values.total);
    byId("checkout-button-total").textContent = fixed(values.total);
    byId("mobile-checkout-total").textContent = fixed(values.total);
    if (state.payments.length === 1 && state.payments[0].automatic) {
      state.payments[0].amount = values.total;
      state.payments[0].received = values.total;
    }
    renderPayments();
    updateCheckoutAvailability();
  }

  function paymentBreakdown() {
    const saleTotal = totals().total;
    const nonCashTotal = state.payments.reduce((sum, payment) => {
      const means = state.means.find((item) => item.id === payment.meansId);
      return sum + (means?.kind === "CASH" ? 0 : number(payment.amount));
    }, 0);
    let cashPending = Math.max(saleTotal - nonCashTotal, 0);
    const rows = state.payments.map((payment) => {
      const means = state.means.find((item) => item.id === payment.meansId);
      const isCash = means?.kind === "CASH";
      const entered = isCash ? number(payment.received) : number(payment.amount);
      const applied = isCash ? Math.min(entered, cashPending) : entered;
      if (isCash) cashPending = Math.max(cashPending - applied, 0);
      return {
        payment,
        means,
        entered,
        applied,
        change: isCash ? Math.max(entered - applied, 0) : 0,
      };
    });
    const appliedTotal = rows.reduce((sum, row) => sum + row.applied, 0);
    return {
      rows,
      appliedTotal,
      changeTotal: rows.reduce((sum, row) => sum + row.change, 0),
      difference: appliedTotal - saleTotal,
    };
  }

  function paymentRow(payment) {
    return paymentBreakdown().rows.find((row) => row.payment.key === payment.key);
  }

  function paymentTotal() {
    return paymentBreakdown().appliedTotal;
  }

  function cashChangeTotal() {
    return paymentBreakdown().changeTotal;
  }

  function renderPaymentDifference() {
    const difference = paymentBreakdown().difference;
    const label = byId("payment-balance-label");
    const amount = byId("payment-balance");
    label.textContent = state.paymentCondition === "CREDIT" ? "Saldo a crédito" : "Diferencia";
    const visibleValue = state.paymentCondition === "CREDIT" ? -Math.abs(difference) : difference;
    amount.textContent = `${visibleValue > 0.005 ? "+" : ""}${fixed(visibleValue)}`;
    amount.parentElement.classList.toggle("is-negative", visibleValue < -0.005);
    amount.parentElement.classList.toggle("is-positive", visibleValue > 0.005);
  }

  function refreshPaymentCalculations() {
    const breakdown = paymentBreakdown();
    breakdown.rows.forEach((item) => {
      const row = byId("payment-lines").querySelector(`[data-payment-key="${item.payment.key}"]`);
      const change = row?.querySelector(".pos-payment-change strong");
      if (change) change.textContent = `${currencySymbol()} ${fixed(item.change)}`;
    });
    renderPaymentDifference();
  }

  function defaultMeans() {
    return state.means.find((item) => item.kind === "CASH") || state.means[0] || null;
  }

  function ensureDefaultPayment(force = false) {
    if (state.paymentCondition === "CREDIT") {
      state.payments = [];
      renderPayments();
      return;
    }
    if (state.payments.length && !force) return;
    const means = defaultMeans();
    state.payments = means ? [{
      key: ++state.paymentSequence,
      meansId: means.id,
      amount: totals().total,
      received: totals().total,
      reference: "",
      automatic: true,
    }] : [];
    renderPayments();
  }

  function renderPayments() {
    const container = byId("payment-lines");
    if (!state.means.length) {
      container.innerHTML = '<div class="pos-no-results">Configure al menos un medio de pago.</div>';
    } else if (!state.payments.length) {
      container.innerHTML = state.paymentCondition === "CREDIT"
        ? '<div class="pos-no-results">Sin adelanto. El total quedará pendiente.</div>'
        : '<div class="pos-no-results">Agregue un medio de pago.</div>';
    } else {
      container.innerHTML = state.payments.map((payment) => {
        const means = state.means.find((item) => item.id === payment.meansId) || state.means[0];
        const isCash = means?.kind === "CASH";
        const requiresReference = Boolean(means && means.kind !== "CASH");
        const row = paymentRow(payment);
        return `
          <div class="pos-payment-row" data-payment-key="${payment.key}">
            <label class="pos-payment-field"><span>Medio de pago</span><select data-payment-action="means" aria-label="Medio de pago">
              ${state.means.map((item) => `<option value="${item.id}" ${item.id === means?.id ? "selected" : ""}>${escapeHtml(item.name)}</option>`).join("")}
            </select></label>
            <label class="pos-payment-field"><span>${isCash ? "Monto recibido" : "Monto pagado"}</span><input data-payment-action="${isCash ? "received" : "amount"}" type="number" min="0" step="0.01" value="${fixed(isCash ? payment.received : payment.amount)}" aria-label="${isCash ? "Efectivo recibido" : "Monto pagado"}"></label>
            <button class="pos-payment-remove" data-payment-action="remove" type="button" aria-label="Quitar pago" ${state.paymentCondition === "CASH" && state.payments.length === 1 ? "disabled" : ""}><i class="ti ti-x"></i></button>
            ${isCash ? `<div class="pos-payment-change"><span>Vuelto</span><strong>${currencySymbol()} ${fixed(row?.change || 0)}</strong></div>` : ""}
            ${requiresReference ? `<label class="pos-payment-field pos-payment-reference ${payment.reference.trim() ? "" : "has-warning"}"><span>N.º de operación / voucher <em>Recomendado</em></span><input class="${payment.reference.trim() ? "" : "is-warning"}" data-payment-action="reference" maxlength="120" value="${escapeHtml(payment.reference)}" placeholder="Ej.: OP003457" aria-label="Número de operación o voucher" aria-describedby="payment-reference-warning-${payment.key}"><small id="payment-reference-warning-${payment.key}" class="pos-payment-reference-warning" role="status" ${payment.reference.trim() ? "hidden" : ""}><i class="ti ti-alert-triangle"></i> Puedes continuar, pero el pago quedará sin referencia para su conciliación.</small></label>` : ""}
          </div>`;
      }).join("");
    }
    renderPaymentDifference();
    updateCheckoutAvailability();
  }

  function selectCustomer(customer) {
    state.selectedCustomer = customer;
    markSaleDirty();
    const card = byId("selected-customer");
    const search = byId("customer-search");
    card.hidden = !customer;
    search.parentElement.hidden = Boolean(customer);
    if (customer) {
      byId("customer-name").textContent = customer.legal_name;
      byId("customer-document").textContent = customer.document_number || "Sin documento";
      byId("customer-address").textContent = customer.address || "Dirección no registrada";
      search.value = "";
      byId("customer-results").hidden = true;
      state.customerResults = [];
      state.activeCustomerIndex = -1;
    }
    updateCheckoutAvailability();
  }

  function checkoutProblem() {
    if (!state.session) return "Abra una sesión de caja.";
    if (!state.cart.size) return "Agregue al menos un producto.";
    if (!byId("document-series").value) return "Configure una serie para el documento.";
    if (state.paymentCondition === "CASH" && !state.payments.length) {
      return "Agregue un medio de pago.";
    }
    if (
      state.paymentCondition === "CASH"
      && paymentBreakdown().difference < -0.009
    ) return `Falta cobrar ${currencySymbol()} ${fixed(Math.abs(paymentBreakdown().difference))}.`;
    if (state.paymentCondition === "CASH" && paymentBreakdown().difference > 0.009) {
      return "Los pagos no efectivos superan el total de la venta.";
    }
    if (state.paymentCondition === "CREDIT") {
      if (!byId("payment-method").value) return "Configure una condición comercial de crédito.";
      if (!byId("credit-due-date").value) return "Indique la fecha de vencimiento.";
      if (byId("credit-due-date").value < localDate()) return "El vencimiento no puede ser anterior a hoy.";
      if (!state.selectedCustomer?.document_number) return "El crédito requiere un cliente identificado.";
      if (paymentTotal() - totals().total > 0.009) return "El adelanto no puede superar el total.";
    }
    for (const payment of state.payments) {
      const means = state.means.find((item) => item.id === payment.meansId);
      const entered = means?.kind === "CASH" ? number(payment.received) : number(payment.amount);
      if (!means || entered <= 0) return "Revise los importes de pago.";
    }
    if (state.documentType === "01") {
      if (!state.selectedCustomer || state.selectedCustomer.document_number?.length !== 11) {
        return "La factura requiere un cliente con RUC de 11 dígitos.";
      }
    }
    return null;
  }

  function updateCheckoutAvailability() {
    const problem = checkoutProblem();
    const disabled = Boolean(problem) || state.busy || !hasPermission("sell.pos");
    byId("checkout-button").disabled = disabled;
    byId("save-draft-button").disabled = Boolean(draftProblem()) || state.busy || !hasPermission("sell.pos");
    byId("mobile-checkout-button").disabled = !state.cart.size || !state.session;
    byId("checkout-button").title = problem || "Registrar venta";
  }

  function renderProductResults(products) {
    state.productResults = products;
    state.activeProductIndex = products.length ? 0 : -1;
    const container = byId("product-results");
    if (!products.length) {
      const canCreate = hasPermission("create.pos.product");
      container.innerHTML = `<div class="pos-no-results">No se encontraron productos.${canCreate ? `<button class="btn btn-sm btn-primary ms-2" type="button" data-create-product><i class="ti ti-plus me-1"></i>Crear producto</button>` : ""}<button class="btn btn-sm btn-outline-primary ms-2" type="button" data-create-manual-line><i class="ti ti-file-plus me-1"></i>Agregar línea libre</button></div>`;
    } else {
      container.innerHTML = products.map((product, index) => {
        const net = number(product.unit_price);
        const gross = product.unit_price === null ? null : net * (product.tax_type === "10" ? 1 + number(product.igv_rate) / 100 : 1);
        return `
          <button class="pos-result ${index === 0 ? "is-active" : ""}" type="button" role="option" aria-selected="${index === 0 ? "true" : "false"}" data-product-id="${product.id}">
            <strong>${escapeHtml(product.sku)}</strong>
            <span>${escapeHtml(product.name)}</span>
            <span class="pos-result__stock">${fixed(product.stock, 3)} ${escapeHtml(product.stock_unit || product.unit)}</span>
            <span class="pos-result__price">${gross === null ? "Sin precio" : `${currencySymbol()} ${fixed(gross)}`}</span>
          </button>`;
      }).join("");
    }
    container.hidden = false;
    byId("product-search").setAttribute("aria-expanded", "true");
  }

  function populatePriceLists() {
    const select = byId("sale-price-list");
    const defaultId = state.register?.default_price_list || "";
    state.selectedPriceList = state.priceLists.some((item) => item.id === defaultId) ? defaultId : null;
    const options = state.priceLists.map((item) => `<option value="${item.id}">${escapeHtml(item.name)}</option>`);
    if (!defaultId) options.unshift('<option value="">Precio base del producto</option>');
    select.innerHTML = options.join("") || '<option value="">Precio base del producto</option>';
    select.value = state.selectedPriceList || "";
    select.disabled = !hasPermission("change.pos.pricelist") || state.priceLists.length < 2;
  }

  function renderCategoryFilters() {
    const container = byId("category-filters");
    const categories = [{ id: "", name: "Todos" }, ...state.categories];
    container.innerHTML = categories.map((category) => `
      <button type="button" data-category-id="${category.id}" class="${state.selectedCategory === category.id ? "active" : ""}">
        ${escapeHtml(category.name)}${category.product_count === undefined ? "" : ` <span>${category.product_count}</span>`}
      </button>`).join("");
  }

  function productQuery(search = "", categoryId = "") {
    const params = new URLSearchParams({
      register_id: state.register.id,
      search,
      currency: state.currency,
    });
    if (state.selectedPriceList) params.set("price_list_id", state.selectedPriceList);
    if (categoryId) params.set("category_id", categoryId);
    return params;
  }

  async function repriceCart(priceListId) {
    if (!state.cart.size) {
      state.selectedPriceList = priceListId || null;
      if (state.productSearchMode === "CATALOG") await loadCatalog();
      return;
    }
    const params = productQuery();
    params.delete("search");
    params.delete("category_id");
    const catalogLines = [...state.cart.values()].filter((line) => !line.manual);
    if (!catalogLines.length) {
      state.selectedPriceList = priceListId || null;
      markSaleDirty();
      if (state.productSearchMode === "CATALOG") await loadCatalog();
      return;
    }
    params.set("product_ids", catalogLines.map((line) => line.productId || line.id).join(","));
    if (priceListId) params.set("price_list_id", priceListId);
    else params.delete("price_list_id");
    const products = await api(`${endpoints.products}?${params}`);
    const productsById = new Map(products.map((item) => [item.id, item]));
    const changes = [];
    for (const line of catalogLines) {
      const product = productsById.get(line.productId || line.id);
      const unit = product?.units?.find((item) => item.id === line.unitId);
      if (!product || !unit || unit.unit_price === null) {
        throw new Error(`No existe precio para ${line.name} en la lista seleccionada.`);
      }
      changes.push({ line, product, unit });
    }
    changes.forEach(({ line, product, unit }) => {
      line.units = product.units;
      line.netPrice = number(unit.unit_price);
      line.originalNetPrice = number(unit.unit_price);
      line.priceChanged = false;
      line.baseStock = number(product.stock);
      line.stock = line.baseStock / line.conversionFactor;
    });
    state.selectedPriceList = priceListId || null;
    markSaleDirty();
    renderCart();
    if (state.productSearchMode === "CATALOG") await loadCatalog();
  }

  function renderCatalog(products) {
    state.catalogProducts = products;
    const container = byId("product-catalog");
    container.innerHTML = products.length
      ? products.map((product) => {
        const net = number(product.unit_price);
        const gross = product.unit_price === null ? null : net * (product.tax_type === "10" ? 1 + number(product.igv_rate) / 100 : 1);
        return `<button class="pos-product-card" type="button" data-catalog-product-id="${product.id}" ${gross === null ? "disabled" : ""}>
          <span class="pos-product-card__visual">${product.image ? `<img src="${escapeHtml(product.image)}" alt="">` : '<i class="ti ti-package"></i>'}</span>
          <span class="pos-product-card__body">
            <strong>${escapeHtml(product.name)}</strong>
            <small>${escapeHtml(product.sku)} · Stock ${fixed(product.stock, 3)} ${escapeHtml(product.stock_unit || product.unit)}</small>
            <b>${gross === null ? "Sin precio" : `${currencySymbol()} ${fixed(gross)}`}</b>
          </span>
        </button>`;
      }).join("")
      : '<div class="pos-catalog-empty">No hay productos disponibles en esta categoría.</div>';
  }

  async function loadCatalog(search = byId("product-search").value.trim()) {
    if (!state.register) return;
    const requestNumber = ++state.catalogRequest;
    const categoryId = state.selectedCategory;
    byId("product-catalog").innerHTML = '<div class="pos-catalog-empty">Cargando productos…</div>';
    try {
      const products = await api(`${endpoints.products}?${productQuery(search, categoryId)}`);
      if (
        requestNumber === state.catalogRequest
        && search === byId("product-search").value.trim()
        && categoryId === state.selectedCategory
      ) renderCatalog(products);
    } catch (error) {
      if (requestNumber !== state.catalogRequest) return;
      byId("product-catalog").innerHTML = '<div class="pos-catalog-empty">No fue posible cargar el catálogo.</div>';
      showAlert(error.message);
    }
  }

  function hideProductResults() {
    state.productResults = [];
    state.activeProductIndex = -1;
    byId("product-results").hidden = true;
    byId("product-search").setAttribute("aria-expanded", "false");
  }

  function moveProductSelection(direction) {
    if (!state.productResults.length) return;
    state.activeProductIndex = (
      state.activeProductIndex + direction + state.productResults.length
    ) % state.productResults.length;
    byId("product-results").querySelectorAll("[data-product-id]").forEach((item, index) => {
      const active = index === state.activeProductIndex;
      item.classList.toggle("is-active", active);
      item.setAttribute("aria-selected", active ? "true" : "false");
      if (active) item.scrollIntoView({ block: "nearest" });
    });
  }

  let productSearchTimer = null;
  async function searchProducts() {
    const search = byId("product-search").value.trim();
    if (!search || !state.register) {
      hideProductResults();
      return;
    }
    try {
      const params = productQuery(search, state.selectedCategory);
      const products = await api(`${endpoints.products}?${params}`);
      if (byId("product-search").value.trim() === search) {
        renderProductResults(products);
      }
    } catch (error) {
      showAlert(error.message);
    }
  }

  function openQuickProduct() {
    if (!hasPermission("create.pos.product")) return showAlert("No tiene permiso para crear productos desde el POS.");
    byId("quick-product-form").reset();
    byId("quick-product-name").value = byId("product-search").value.trim();
    byId("quick-product-stock").checked = true;
    byId("quick-product-includes-tax").checked = true;
    byId("quick-product-error").hidden = true;
    byId("quick-product-unit").innerHTML = state.units.map((item) => `<option value="${item.id}" ${item.code === "NIU" ? "selected" : ""}>${escapeHtml(item.code)} · ${escapeHtml(item.name)}</option>`).join("");
    byId("quick-product-category").innerHTML = '<option value="">Sin categoría</option>' + state.productCategories.map((item) => `<option value="${item.id}">${escapeHtml(item.name)}</option>`).join("");
    openDialog(byId("quick-product-dialog"));
    setTimeout(() => (byId("quick-product-name").value ? byId("quick-product-sku") : byId("quick-product-name")).focus(), 30);
  }

  async function createQuickProduct(event) {
    event.preventDefault();
    const errorBox = byId("quick-product-error");
    errorBox.hidden = true;
    setBusy(true, "Creando producto…");
    try {
      const created = await api(endpoints.productCreate, {
        method: "POST",
        body: JSON.stringify({
          name: byId("quick-product-name").value.trim(),
          sku: byId("quick-product-sku").value.trim(),
          barcode: byId("quick-product-barcode").value.trim(),
          sale_price: fixed(byId("quick-product-price").value),
          includes_tax: byId("quick-product-includes-tax").checked,
          tax_type: byId("quick-product-tax").value,
          unit_id: byId("quick-product-unit").value,
          category_id: byId("quick-product-category").value || null,
          tracks_inventory: byId("quick-product-stock").checked,
        }),
      });
      const params = productQuery();
      params.delete("search");
      params.set("product_ids", created.id);
      const products = await api(`${endpoints.products}?${params}`);
      if (!products.length) throw new Error("El producto se creó, pero no pudo recuperarse para la venta.");
      addProduct(products[0]);
      closeDialog(byId("quick-product-dialog"));
      showAlert(`Producto ${products[0].sku} creado y agregado a la venta.`, "success");
    } catch (error) {
      errorBox.querySelector("span").textContent = error.message;
      errorBox.hidden = false;
    } finally {
      setBusy(false);
    }
  }

  function addManualLine() {
    if (!state.session) return showAlert("Abra una sesión de caja antes de agregar una línea libre.");
    const unit = state.units.find((item) => item.code === "NIU") || state.units[0];
    if (!unit) return showAlert("Configure al menos una unidad de medida antes de agregar una línea libre.");
    const search = byId("product-search").value.trim();
    const description = search || "Producto o servicio sin registrar";
    const quantity = 1;
    const finalPrice = 0;
    const taxType = "10";
    const igvRate = number(state.taxRates[taxType] || 0);
    const lineId = `manual-${uuid()}`;
    const netPrice = taxType === "10" ? finalPrice / (1 + igvRate / 100) : finalPrice;
    state.cart.set(lineId, {
      id: lineId, productId: null, manual: true,
      manualKind: "PRODUCT",
      sku: "SIN CODIGO",
      name: description,
      unitId: unit.id, unit: unit.code,
      units: [{ id: unit.id, code: unit.code, conversion_factor: "1", unit_price: fixed(netPrice, 6), is_default_sale: true }],
      conversionFactor: 1,
      netPrice: number(netPrice.toFixed(6)),
      originalNetPrice: number(netPrice.toFixed(6)),
      priceChanged: false, quantity, discount: 0,
      memo: "",
      taxType, igvRate, baseStock: 0, stock: 0,
      stockUnit: unit.code, tracksInventory: false,
    });
    state.activeCartLineId = lineId;
    markSaleDirty();
    byId("product-search").value = "";
    hideProductResults();
    renderCart();
    requestAnimationFrame(() => {
      const selector = search ? '[data-action="price"]' : '[data-action="description"]';
      const input = byId("cart-lines").querySelector(`[data-line-id="${lineId}"] ${selector}`);
      input?.focus();
      input?.select();
    });
  }

  async function openProductCommercial(productId, view) {
    const line = state.cart.get(productId);
    if (!line) return;
    byId("product-commercial-title").textContent = view === "prices" ? "Listas de precios" : "Stock por almacén";
    byId("product-commercial-subtitle").textContent = `${line.sku} · ${line.name}`;
    byId("product-commercial-content").innerHTML = '<div class="pos-no-results">Cargando información…</div>';
    openDialog(byId("product-commercial-dialog"));
    try {
      const url = endpoints.productCommercial.replace("{id}", encodeURIComponent(productId));
      const data = await api(url);
      if (view === "prices") {
        const rows = [
          { name: "Precio base", currency: data.base_price.currency, amount: data.base_price.amount, is_default: false },
          ...data.prices,
        ];
        byId("product-commercial-content").innerHTML = `<div class="pos-commercial-list">${rows.map((item) => `<div><span><i class="ti ti-tag"></i><strong>${escapeHtml(item.name)}</strong>${item.is_default ? "<small>Predeterminada</small>" : ""}</span><b>${escapeHtml(currencySymbol(item.currency))} ${fixed(item.amount)}</b></div>`).join("")}</div>`;
      } else {
        byId("product-commercial-content").innerHTML = data.product.tracks_inventory
          ? `<div class="pos-commercial-list">${data.warehouses.length ? data.warehouses.map((item) => `<div class="${item.is_current ? "is-current" : ""}"><span><i class="ti ti-building-warehouse"></i><strong>${escapeHtml(item.warehouse)}</strong><small>${escapeHtml(item.store)}${item.is_current ? " · Sucursal actual" : ""}</small></span><b>${fixed(item.quantity, 3)} ${escapeHtml(data.product.unit)}</b></div>`).join("") : '<div class="pos-no-results">No existen almacenes activos.</div>'}</div>`
          : '<div class="pos-no-results">Este producto o servicio no controla existencias.</div>';
      }
    } catch (error) {
      byId("product-commercial-content").innerHTML = `<div class="pos-form-error"><i class="ti ti-alert-circle"></i><span>${escapeHtml(error.message)}</span></div>`;
    }
  }

  let customerSearchTimer = null;
  async function searchCustomers() {
    const search = byId("customer-search").value.trim();
    if (search.length < 2) {
      state.customerResults = [];
      state.activeCustomerIndex = -1;
      byId("customer-results").hidden = true;
      return;
    }
    try {
      const customers = await api(`${endpoints.customers}?search=${encodeURIComponent(search)}`);
      if (byId("customer-search").value.trim() !== search) return;
      state.customerResults = customers;
      state.activeCustomerIndex = customers.length ? 0 : -1;
      const container = byId("customer-results");
      container.innerHTML = customers.length
        ? customers.map((customer, index) => `
          <button class="pos-customer-result ${index === 0 ? "is-active" : ""}" type="button" data-customer-id="${customer.id}" role="option" aria-selected="${index === 0 ? "true" : "false"}">
            <strong>${escapeHtml(customer.legal_name)}</strong>
            <span>${escapeHtml(customer.document_number || "Sin documento")}${customer.address ? ` · ${escapeHtml(customer.address)}` : ""}</span>
          </button>`).join("")
        : '<div class="pos-no-results">No se encontraron clientes.</div>';
      container.hidden = false;
    } catch (error) {
      showAlert(error.message);
    }
  }

  function paymentPayload(payment) {
    const row = paymentRow(payment);
    const means = row?.means;
    const amount = row?.applied || 0;
    const received = means?.kind === "CASH" ? row.entered : amount;
    return {
      means_of_payment_id: payment.meansId,
      amount: fixed(amount),
      currency: state.currency,
      exchange_rate: fixed(byId("exchange-rate").value || 1, 6),
      amount_in_sale_currency: fixed(amount),
      received_amount: fixed(received),
      change_amount: fixed(row?.change || 0),
      operation_reference: payment.reference || "",
    };
  }

  function salePayload(includePayments = true) {
    const lines = [...state.cart.values()];
    return {
      register_id: state.register.id,
      cash_session_id: state.session.id,
      idempotency_key: state.idempotencyKey || (state.idempotencyKey = uuid()),
      document_type: state.documentType,
      series_id: byId("document-series").value,
      customer_id: state.selectedCustomer?.id || null,
      payment_condition: state.paymentCondition,
      payment_method_id: byId("payment-method").value || null,
      due_date: state.paymentCondition === "CREDIT" ? byId("credit-due-date").value : null,
      warehouse_id: state.register.default_warehouse || null,
      price_list_id: state.selectedPriceList || null,
      currency: state.currency,
      exchange_rate: fixed(byId("exchange-rate").value || 1, 6),
      global_discount_amount: fixed(totals().globalDiscount),
      global_discount_before_tax: true,
      notes: byId("sale-notes").value.trim(),
      device_identifier: `web-${navigator.userAgentData?.mobile ? "mobile" : "desktop"}`,
      lines: lines.map((line) => ({
        product_id: line.productId || (line.manual ? null : line.id),
        line_type: line.manual ? "MANUAL" : "PRODUCT",
        unit_id: line.unitId,
        description: line.name,
        quantity: fixed(line.quantity, 3),
        unit_price: fixed(line.netPrice, 6),
        discount_amount: fixed(line.discount),
        tax_type: line.taxType,
        igv_rate: fixed(line.igvRate),
        product_code: line.sku,
        memo: line.memo || "",
      })),
      payments: includePayments ? state.payments.map(paymentPayload) : [],
    };
  }

  function draftProblem() {
    if (!state.session) return "Abra una sesión de caja.";
    if (!state.cart.size) return "Agregue al menos un producto.";
    if (!byId("document-series").value) return "Configure una serie para el documento.";
    if (state.documentType === "01" && state.selectedCustomer?.document_number?.length !== 11) {
      return "La factura requiere un cliente con RUC de 11 dígitos.";
    }
    return null;
  }

  async function saveDraft() {
    const problem = draftProblem();
    if (problem) return showAlert(problem);
    setBusy(true, "Guardando borrador…");
    try {
      const result = await api(endpoints.draft, {
        method: "POST",
        body: JSON.stringify(salePayload(false)),
      });
      showAlert(`Borrador ${result.ticket_code} guardado en la caja abierta.`, "success");
      resetSale();
      byId("product-search").focus();
    } catch (error) {
      showAlert(error.message);
    } finally {
      setBusy(false);
    }
  }

  async function discardDraft() {
    if (!state.draftTransactionId || !confirm("¿Descartar este borrador? Esta acción no mueve stock.")) return;
    setBusy(true, "Descartando borrador…");
    try {
      const url = endpoints.recentSales.replace(
        /sales\/recent\/?$/,
        `sales/${encodeURIComponent(state.draftTransactionId)}/cancel-draft/`,
      );
      await api(url, { method: "POST", body: JSON.stringify({}) });
      resetSale();
      showAlert("Borrador descartado. Ya no bloqueará el cierre de caja.", "success");
    } catch (error) {
      showAlert(error.message);
    } finally {
      setBusy(false);
    }
  }

  function openLineMemo(lineId = state.activeCartLineId) {
    const line = state.cart.get(lineId);
    if (!line) return;
    state.memoLineId = line.id;
    byId("line-memo-product").textContent = `${line.sku} · ${line.name}`;
    byId("line-memo-text").value = line.memo || "";
    byId("line-memo-count").textContent = `${byId("line-memo-text").value.length}/500`;
    openDialog(byId("line-memo-dialog"));
    setTimeout(() => byId("line-memo-text").focus(), 30);
  }

  function saveLineMemo(event) {
    event.preventDefault();
    const line = state.cart.get(state.memoLineId);
    if (!line) return;
    line.memo = byId("line-memo-text").value.trim().slice(0, 500);
    markSaleDirty();
    closeDialog(byId("line-memo-dialog"));
    state.memoLineId = null;
    renderCart();
  }

  async function checkout() {
    if (state.busy) return;
    const problem = checkoutProblem();
    if (problem) {
      showAlert(problem);
      return;
    }
    const cartSnapshot = [...state.cart.values()].map((line) => ({ ...line }));
    setBusy(true, "Registrando venta…");
    hideAlert();
    try {
      const payload = salePayload(true);
      const result = await api(endpoints.checkout, { method: "POST", body: JSON.stringify(payload) });
      renderReceipt(result, cartSnapshot);
      closeDialog(byId("checkout-review-dialog"));
      resetSale();
      document.body.classList.remove("pos-checkout-open");
      openDialog(byId("success-dialog"));
    } catch (error) {
      showAlert(error.message);
    } finally {
      setBusy(false);
    }
  }

  function renderCheckoutReview() {
    const values = totals();
    byId("confirm-checkout-button").innerHTML = state.paymentCondition === "CREDIT"
      ? '<i class="ti ti-check me-1"></i>Confirmar venta a crédito'
      : '<i class="ti ti-check me-1"></i>Confirmar y cobrar';
    const documentLabels = { NV: "Nota de venta", "03": "Boleta", "01": "Factura" };
    const lines = [...state.cart.values()].map((line) => {
      const lineValue = lineTotals(line);
      return `<tr><td><strong>${escapeHtml(line.name)}</strong>${line.memo ? `<small>${escapeHtml(line.memo)}</small>` : ""}</td><td>${fixed(line.quantity, number(line.quantity) % 1 ? 3 : 0)}</td><td>${currencySymbol()} ${fixed(grossUnitPrice(line))}</td><td>${currencySymbol()} ${fixed(lineValue.total)}</td></tr>`;
    }).join("");
    const payments = paymentBreakdown().rows.map((row) => {
      const { payment, means } = row;
      const isCash = means?.kind === "CASH";
      const referenceDetail = payment.reference
        ? `<small>Operación: ${escapeHtml(payment.reference)}</small>`
        : (!isCash ? '<small class="pos-review-warning"><i class="ti ti-alert-triangle"></i> Sin número de operación / voucher</small>' : "");
      return `<tr><td><strong>${escapeHtml(means?.name || "Medio de pago")}</strong>${referenceDetail}</td><td>${currencySymbol()} ${fixed(row.applied)}</td><td>${currencySymbol()} ${fixed(row.entered)}</td><td>${isCash ? `${currencySymbol()} ${fixed(row.change)}` : "—"}</td></tr>`;
    }).join("");
    const customer = state.selectedCustomer
      ? `${escapeHtml(state.selectedCustomer.legal_name)} · ${escapeHtml(state.selectedCustomer.document_number || "Sin documento")}`
      : "VARIOS · Sin documento";
    byId("checkout-review-content").innerHTML = `
      <div class="pos-review-meta"><div><span>Documento</span><strong>${escapeHtml(documentLabels[state.documentType] || state.documentType)} · ${escapeHtml(byId("document-series").selectedOptions[0]?.textContent || "")}</strong></div><div><span>Cliente</span><strong>${customer}</strong></div></div>
      <section class="pos-review-section"><h3>Productos</h3><div class="pos-review-table-wrap"><table><thead><tr><th>Producto</th><th>Cant.</th><th>Precio</th><th>Total</th></tr></thead><tbody>${lines}</tbody></table></div></section>
      <div class="pos-review-totals"><span>Subtotal <strong>${currencySymbol()} ${fixed(values.subtotal)}</strong></span><span>Descuentos <strong>− ${currencySymbol()} ${fixed(values.discount)}</strong></span><span>IGV <strong>${currencySymbol()} ${fixed(values.tax)}</strong></span><span class="is-total">Total a pagar <strong>${currencySymbol()} ${fixed(values.total)}</strong></span></div>
      <section class="pos-review-section"><h3>Distribución del cobro</h3><div class="pos-review-table-wrap"><table><thead><tr><th>Medio</th><th>Aplicado</th><th>Recibido</th><th>Vuelto</th></tr></thead><tbody>${payments || '<tr><td colspan="4">Sin pago inmediato</td></tr>'}</tbody></table></div></section>
      <div class="pos-review-settlement"><span>Total aplicado <strong>${currencySymbol()} ${fixed(paymentTotal())}</strong></span><span>Vuelto al cliente <strong>${currencySymbol()} ${fixed(cashChangeTotal())}</strong></span></div>`;
  }

  function prepareCheckoutReview() {
    const problem = checkoutProblem();
    if (problem) return showAlert(problem);
    hideAlert();
    renderCheckoutReview();
    openDialog(byId("checkout-review-dialog"));
    setTimeout(() => byId("confirm-checkout-button").focus(), 30);
  }

  function renderReceipt(result, lines) {
    state.currentReceipt = result;
    const documentLabels = {
      NV: "NOTA DE VENTA",
      "03": "BOLETA",
      "01": "FACTURA",
    };
    // Prefer the persisted snapshot: it contains the definitive description and memo.
    const sourceLines = result.lines?.length ? result.lines : lines || [];
    const symbol = currencySymbol(result.currency);
    const receiptLines = sourceLines
      .map((line) => {
        const lineName =
          line.name || line.description || line.product_code || "Producto";
        const lineTotal =
          line.total === undefined ? lineTotals(line).total : line.total;
        const code = line.sku || line.product_code || "SIN CÓDIGO";
        const unit = line.unit || line.unit_code || "NIU";
        const unitPrice =
          line.netPrice === undefined ? line.unit_price : line.netPrice;
        const memo = String(line.memo || "").trim();
        const discount = number(line.discount_amount ?? line.discountAmount);
        return `<div class="pos-receipt__item">
        <div class="pos-receipt__item-name">${escapeHtml(lineName)}</div>
        <div class="pos-receipt__item-code">${escapeHtml(code)} · ${escapeHtml(unit)}</div>
        ${memo ? `<div class="pos-receipt__item-memo">Detalle: ${escapeHtml(memo)}</div>` : ""}
        <div class="pos-receipt__row pos-receipt__item-values">
          <span>${fixed(line.quantity, number(line.quantity) % 1 ? 3 : 0)} × ${symbol} ${fixed(unitPrice)}</span>
          <strong>${symbol} ${fixed(lineTotal)}</strong>
        </div>
        ${discount > 0 ? `<div class="pos-receipt__row pos-receipt__discount"><span>Descuento del ítem</span><span>- ${symbol} ${fixed(discount)}</span></div>` : ""}
      </div>`;
      })
      .join("");
    const companyLogo = result.company_logo_url
      ? `<img class="pos-receipt__logo" src="${escapeHtml(result.company_logo_url)}" alt="${escapeHtml(result.company_name || "Empresa")}">`
      : `<div class="pos-receipt__company-name">${escapeHtml(result.company_name || "EMPRESA")}</div>`;
    const companyContact = [result.company_phone, result.company_email]
      .filter(Boolean)
      .join(" · ");
    const customerDocument = [
      result.customer_document_type,
      result.customer_document_number,
    ]
      .filter(Boolean)
      .join(": ");
    const paymentLines = (result.payments || [])
      .map(
        (payment) => `
      <div class="pos-receipt__payment">
        <div class="pos-receipt__row"><span>${escapeHtml(payment.means_of_payment_name || "Pago")}</span><strong>${symbol} ${fixed(payment.amount_in_sale_currency ?? payment.amount)}</strong></div>
        ${payment.operation_reference ? `<div class="pos-receipt__meta">Operación: ${escapeHtml(payment.operation_reference)}</div>` : ""}
        ${number(payment.change_amount) > 0 ? `<div class="pos-receipt__row"><span>Vuelto</span><span>${symbol} ${fixed(payment.change_amount)}</span></div>` : ""}
      </div>`,
      )
      .join("");
    const electronicLabels = {
      ACCEPTED: "Aceptado por SUNAT",
      REJECTED: "Rechazado por SUNAT",
      ERROR: "Error de envío electrónico",
      PENDING: "Pendiente de envío electrónico",
    };
    const electronicNotice = electronicLabels[result.electronic_status]
      ? `<div class="pos-receipt__electronic"><strong>${escapeHtml(electronicLabels[result.electronic_status])}</strong>${result.electronic_message ? `<br><span>${escapeHtml(result.electronic_message)}</span>` : ""}</div>`
      : "";
    byId("pos-receipt").innerHTML = `
      <div class="pos-receipt__header">
        ${companyLogo}
        ${result.company_logo_url && result.company_name ? `<div class="pos-receipt__company-name">${escapeHtml(result.company_name)}</div>` : ""}
        ${result.company_ruc ? `<div>RUC ${escapeHtml(result.company_ruc)}</div>` : ""}
        ${result.company_address ? `<div>${escapeHtml(result.company_address)}</div>` : ""}
        ${companyContact ? `<div>${escapeHtml(companyContact)}</div>` : ""}
        ${result.store_name ? `<div class="pos-receipt__store">${escapeHtml(result.store_name)}${result.store_address ? ` · ${escapeHtml(result.store_address)}` : ""}</div>` : ""}
      </div>
      <div class="pos-receipt__document">
        <strong>${escapeHtml(documentLabels[result.document_type] || "COMPROBANTE")}</strong>
        <span>${escapeHtml(result.document_series)}-${escapeHtml(result.document_number)}</span>
        <small>Ticket ${escapeHtml(result.ticket_code || "")}</small>
      </div>
      <div class="pos-receipt__section">
      <div class="pos-receipt__row"><span>Cliente</span><span>${escapeHtml(result.customer_name || "VARIOS")}</span></div>
      ${customerDocument ? `<div class="pos-receipt__row"><span>Documento</span><span>${escapeHtml(customerDocument)}</span></div>` : ""}
      ${result.customer_address ? `<div class="pos-receipt__row"><span>Dirección</span><span>${escapeHtml(result.customer_address)}</span></div>` : ""}
      <div class="pos-receipt__row"><span>Fecha</span><span>${new Date(result.completed_at || Date.now()).toLocaleString("es-PE")}</span></div>
      ${result.cashier_name ? `<div class="pos-receipt__row"><span>Cajero(a)</span><span>${escapeHtml(result.cashier_name)}</span></div>` : ""}
      ${result.register_name ? `<div class="pos-receipt__row"><span>Caja</span><span>${escapeHtml(result.register_name)}</span></div>` : ""}
      <div class="pos-receipt__row"><span>Condición</span><span>${result.payment_condition === "CREDIT" ? "CRÉDITO" : "CONTADO"}</span></div>
      ${result.due_date ? `<div class="pos-receipt__row"><span>Vencimiento</span><span>${escapeHtml(result.due_date)}</span></div>` : ""}
      </div>
      <div class="pos-receipt__items">
      ${receiptLines}
      </div>
      <div class="pos-receipt__totals">
        <div class="pos-receipt__row"><span>Subtotal</span><span>${symbol} ${escapeHtml(result.subtotal)}</span></div>
        <div class="pos-receipt__row"><span>Descuentos</span><span>- ${symbol} ${fixed(result.total_discount)}</span></div>
        <div class="pos-receipt__row"><span>IGV</span><span>${symbol} ${escapeHtml(result.igv_total)}</span></div>
        <div class="pos-receipt__row pos-receipt__total"><span>TOTAL</span><span>${symbol} ${escapeHtml(result.total)}</span></div>
        ${number(result.outstanding_amount) > 0 ? `<div class="pos-receipt__row pos-receipt__outstanding"><strong>SALDO PENDIENTE</strong><strong>${symbol} ${escapeHtml(result.outstanding_amount)}</strong></div>` : ""}
      </div>
      ${paymentLines ? `<div class="pos-receipt__payments"><div class="pos-receipt__caption">PAGOS</div>${paymentLines}</div>` : ""}
      ${result.notes ? `<div class="pos-receipt__notes"><strong>Observaciones</strong><br>${escapeHtml(result.notes)}</div>` : ""}
      ${electronicNotice}
      <div class="pos-receipt__footer">${["01", "03"].includes(result.document_type) ? "Representación impresa del comprobante electrónico.<br>" : ""}Gracias por su compra.</div>
      <div class="text-center small">Powered by APUDIG</div>`;
    byId("receipt-a4-button").href = result.document_pdf_url || "#";
    byId("return-sale-button").hidden = !(
      hasPermission("refund.pos.sale") &&
      result.status === "COMPLETED" &&
      result.payment_status === "PAID"
    );
    byId("debit-note-button").hidden = !(
      hasPermission("issue.pos.invoice") &&
      result.status === "COMPLETED" &&
      (["01", "03"].includes(result.document_type) ||
        result.billing_status === "INVOICED")
    );
  }

  function openReturnDialog() {
    const receipt = state.currentReceipt;
    if (!receipt || !state.session) {
      showAlert("La devolución requiere un comprobante y una caja abierta.");
      return;
    }
    const availableLines = (receipt.lines || []).map((line) => ({
      ...line,
      available: Math.max(number(line.quantity) - number(line.returned_quantity), 0),
    })).filter((line) => line.available > 0);
    byId("return-lines").innerHTML = availableLines.length ? availableLines.map((line) => `
      <label class="pos-return-line">
        <span><strong>${escapeHtml(line.description || line.product_code)}</strong><small>Disponible: ${fixed(line.available, 3)} ${escapeHtml(line.unit_code)}</small></span>
        <input class="form-control" type="number" min="0" max="${line.available}" step="0.001" value="0" data-return-line-id="${line.id}">
      </label>`).join("") : '<div class="pos-no-results">Todos los productos ya fueron devueltos.</div>';
    const requiresCreditNote = ["01", "03"].includes(receipt.document_type)
      || receipt.billing_status === "INVOICED";
    const creditSeries = selectedSeries("07");
    byId("return-credit-series-wrap").hidden = !requiresCreditNote;
    byId("return-credit-series").required = requiresCreditNote;
    byId("return-credit-series").innerHTML = creditSeries.length
      ? creditSeries.map((item) => `<option value="${item.id}">${escapeHtml(item.series)} · N.º ${item.next_number}</option>`).join("")
      : '<option value="">Sin serie configurada</option>';
    byId("return-means").innerHTML = state.means.map((item) => `
      <option value="${item.id}">${escapeHtml(item.name)}</option>`).join("");
    byId("return-reason").value = "";
    byId("return-reference").value = "";
    state.returnIdempotencyKey = uuid();
    openDialog(byId("return-dialog"));
  }

  async function submitReturn(event) {
    event.preventDefault();
    if (!state.currentReceipt || !state.session) return;
    const lines = [...byId("return-lines").querySelectorAll("[data-return-line-id]")]
      .map((input) => ({ line_id: input.dataset.returnLineId, quantity: input.value }))
      .filter((line) => number(line.quantity) > 0);
    if (!lines.length) {
      showAlert("Indique al menos una cantidad a devolver.");
      return;
    }
    setBusy(true, "Registrando devolución…");
    try {
      const returnUrl = endpoints.recentSales.replace(
        /recent\/?$/,
        `${encodeURIComponent(state.currentReceipt.id)}/return/`,
      );
      const result = await api(returnUrl, {
        method: "POST",
        body: JSON.stringify({
          cash_session_id: state.session.id,
          idempotency_key: state.returnIdempotencyKey,
          credit_note_series_id: byId("return-credit-series-wrap").hidden
            ? null : (byId("return-credit-series").value || null),
          reason_code: "01",
          reason: byId("return-reason").value.trim(),
          refund_means_of_payment_id: byId("return-means").value,
          operation_reference: byId("return-reference").value.trim(),
          lines,
        }),
      });
      closeDialog(byId("return-dialog"));
      closeDialog(byId("success-dialog"));
      state.returnIdempotencyKey = null;
      const note = result.credit_note_number
        ? ` Nota de Crédito ${result.credit_note_series}-${result.credit_note_number}.`
        : "";
      showAlert(`Devolución registrada por ${currencySymbol(result.currency)} ${result.total}.${note}`, "success");
    } catch (error) {
      showAlert(error.message);
    } finally {
      setBusy(false);
    }
  }

  function openDebitNoteDialog() {
    const series = selectedSeries("08");
    byId("debit-note-series").innerHTML = series.length
      ? series.map((item) => `<option value="${item.id}">${escapeHtml(item.series)} · N.º ${item.next_number}</option>`).join("")
      : '<option value="">Sin serie configurada</option>';
    byId("debit-note-description").value = "";
    byId("debit-note-amount").value = "";
    byId("debit-note-reason").value = "";
    state.debitNoteIdempotencyKey = uuid();
    openDialog(byId("debit-note-dialog"));
  }

  async function submitDebitNote(event) {
    event.preventDefault();
    const receipt = state.currentReceipt;
    const sourceLine = receipt?.lines?.[0];
    if (!receipt || !sourceLine) return;
    setBusy(true, "Emitiendo Nota de Débito…");
    try {
      const debitUrl = endpoints.recentSales.replace(
        /recent\/?$/,
        `${encodeURIComponent(receipt.id)}/debit-note/`,
      );
      const result = await api(debitUrl, {
        method: "POST",
        body: JSON.stringify({
          idempotency_key: state.debitNoteIdempotencyKey,
          series_id: byId("debit-note-series").value,
          reason_code: "01",
          reason: byId("debit-note-reason").value.trim(),
          lines: [{
            line_id: sourceLine.id,
            description: byId("debit-note-description").value.trim(),
            quantity: "1.0000",
            unit_price: fixed(byId("debit-note-amount").value, 6),
          }],
        }),
      });
      closeDialog(byId("debit-note-dialog"));
      state.debitNoteIdempotencyKey = null;
      showAlert(`Nota de Débito ${result.series}-${result.number} emitida por ${currencySymbol(result.currency)} ${result.total}.`, "success");
    } catch (error) {
      showAlert(error.message);
    } finally {
      setBusy(false);
    }
  }

  async function loadRecentSales() {
    openDialog(byId("reprint-dialog"));
    const list = byId("recent-sales");
    list.innerHTML = '<div class="pos-no-results">Buscando ventas y borradores…</div>';
    try {
      const params = new URLSearchParams();
      if (state.register) params.set("register_id", state.register.id);
      const scope = byId("recent-sales-scope").value;
      params.set("scope", scope);
      if (scope === "session" && state.session) params.set("cash_session_id", state.session.id);
      if (scope === "day") params.set("date", byId("recent-sales-date").value || localDate());
      const query = `?${params}`;
      const records = await api(`${endpoints.recentSales}${query}`);
      list.innerHTML = records.length ? records.map((record) => {
        const isDraft = record.status === "DRAFT";
        const timestamp = record.completed_at || record.started_at;
        const date = new Date(timestamp);
        const documentCode = isDraft
          ? (record.ticket_code || "Venta sin emitir")
          : `${record.document_series || ""}-${record.document_number || ""}`;
        const customerDocument = record.customer_document_number
          ? ` · ${record.customer_document_number}`
          : "";
        return `<button class="pos-history-card ${isDraft ? "is-draft" : ""}" type="button" ${isDraft ? `data-load-draft-id="${record.id}"` : `data-reprint-id="${record.id}"`}>
          <span class="pos-history-card__top">
            <span class="pos-history-status"><i class="ti ${isDraft ? "ti-pencil" : "ti-circle-check"}"></i>${isDraft ? "Borrador" : "Emitida"}</span>
            <time datetime="${escapeHtml(timestamp || "")}">${date.toLocaleDateString("es-PE")} <b>${date.toLocaleTimeString("es-PE", { hour: "2-digit", minute: "2-digit" })}</b></time>
          </span>
          <span class="pos-history-card__main">
            <span><strong>${escapeHtml(documentCode)}</strong><small>${escapeHtml(record.customer_name || "Cliente general")}${escapeHtml(customerDocument)}</small></span>
            <b class="pos-history-card__total">${escapeHtml(currencySymbol(record.currency))} ${escapeHtml(record.total)}</b>
          </span>
          <span class="pos-history-card__footer">
            <span><i class="ti ti-user"></i>${escapeHtml(record.cashier_name || "Sin usuario")}</span>
            <span><i class="ti ${isDraft ? "ti-edit" : "ti-printer"}"></i>${isDraft ? "Recuperar y editar" : "Ver y reimprimir"}</span>
          </span>
        </button>`;
      }).join("") : '<div class="pos-no-results">No hay ventas ni borradores recientes.</div>';
    } catch (error) {
      list.innerHTML = `<div class="pos-no-results">${escapeHtml(error.message)}</div>`;
    }
  }

  async function loadDraft(transactionId) {
    setBusy(true, "Recuperando borrador…");
    try {
      const detailUrl = endpoints.recentSales.replace(/sales\/recent\/?$/, `sales/${encodeURIComponent(transactionId)}/`);
      const draft = await api(detailUrl);
      if (draft.status !== "DRAFT" || draft.cash_session !== state.session?.id) {
        throw new Error("El borrador ya no pertenece a la caja abierta.");
      }
      const params = productQuery();
      params.delete("search");
      params.delete("category_id");
      params.set("product_ids", draft.lines.map((line) => line.product_id).join(","));
      if (draft.price_list_id) params.set("price_list_id", draft.price_list_id);
      const products = await api(`${endpoints.products}?${params}`);
      const productMap = new Map(products.map((item) => [item.id, item]));
      state.cart.clear();
      draft.lines.forEach((saved) => {
        const product = productMap.get(saved.product_id);
        if (!product) return;
        const units = product.units?.length ? product.units : [];
        const unit = units.find((item) => item.id === saved.unit_id) || units[0];
        const conversionFactor = Math.max(number(unit?.conversion_factor || 1), 0.000001);
        const lineId = saved.is_manual ? `manual-${saved.id}` : product.id;
        state.cart.set(lineId, {
          id: lineId, productId: saved.product_id, manual: Boolean(saved.is_manual),
          sku: saved.product_code || product.sku,
          name: saved.description || product.name, unitId: saved.unit_id || unit?.id,
          unit: saved.unit_code || unit?.code || product.unit, units,
          conversionFactor, netPrice: number(saved.unit_price),
          originalNetPrice: number(unit?.unit_price ?? saved.unit_price), priceChanged: true,
          quantity: number(saved.quantity), discount: number(saved.discount_amount),
          memo: saved.memo || "",
          taxType: saved.tax_type, igvRate: number(saved.igv_rate),
          baseStock: number(product.stock), stock: number(product.stock) / conversionFactor,
          stockUnit: product.stock_unit || product.unit,
          tracksInventory: Boolean(product.tracks_inventory),
        });
      });
      state.idempotencyKey = draft.idempotency_key;
      state.draftTransactionId = draft.id;
      byId("discard-draft-button").hidden = false;
      state.activeCartLineId = state.cart.keys().next().value || null;
      state.globalDiscount = number(draft.global_discount_amount);
      state.currency = draft.currency;
      byId("sale-currency").value = draft.currency;
      state.selectedPriceList = draft.price_list_id || null;
      byId("sale-price-list").value = state.selectedPriceList || "";
      setDocumentType(draft.document_type);
      const series = state.series.find((item) => item.document_type === draft.document_type && item.series === draft.document_series);
      if (series) byId("document-series").value = series.id;
      setPaymentCondition(draft.payment_condition);
      if (draft.payment_method_id) byId("payment-method").value = draft.payment_method_id;
      if (draft.due_date) byId("credit-due-date").value = draft.due_date;
      byId("sale-notes").value = draft.notes || "";
      selectCustomer({
        id: draft.customer_id, legal_name: draft.customer_name,
        document_type: draft.customer_document_type,
        document_number: draft.customer_document_number,
        address: draft.customer_address,
      });
      closeDialog(byId("reprint-dialog"));
      renderCart();
      showAlert(`Borrador ${draft.ticket_code} recuperado. Puede editarlo y cobrarlo.`, "success");
    } catch (error) {
      showAlert(error.message);
    } finally {
      setBusy(false);
    }
  }

  async function prepareReprint(transactionId) {
    setBusy(true, "Preparando reimpresión…");
    try {
      const width = byId("receipt-width").value;
      const reprintUrl = endpoints.recentSales.replace(
        /recent\/?$/,
        `${encodeURIComponent(transactionId)}/reprint/`,
      );
      const result = await api(reprintUrl, {
        method: "POST",
        body: JSON.stringify({ width }),
      });
      closeDialog(byId("reprint-dialog"));
      setReceiptWidth(result.print_width || width);
      renderReceipt(result, result.lines);
      openDialog(byId("success-dialog"));
    } catch (error) {
      showAlert(error.message);
    } finally {
      setBusy(false);
    }
  }

  function setReceiptWidth(width) {
    const normalized = width === "58" ? "58" : "80";
    byId("receipt-width").value = normalized;
    document.body.classList.toggle("pos-print-58", normalized === "58");
    byId("pos-receipt").dataset.width = normalized;
  }

  function resetSale() {
    state.cart.clear();
    state.draftTransactionId = null;
    state.idempotencyKey = null;
    state.activeCartLineId = null;
    state.globalDiscount = 0;
    byId("discard-draft-button").hidden = true;
    markSaleDirty();
    byId("sale-notes").value = "";
    setPaymentCondition("CASH");
    useDefaultCustomer();
    renderCart();
  }

  async function openCashSession(event) {
    event.preventDefault();
    if (!state.register) return;
    setBusy(true, "Abriendo caja…");
    try {
      const denominations = collectDenominations("opening-denominations");
      const payload = {
        register_id: state.register.id,
        opening_total: fixed(byId("opening-total").value),
        currency: byId("opening-currency").value,
        note: byId("opening-note").value.trim(),
      };
      if (denominations.length) payload.denominations = denominations;
      state.session = await api(endpoints.open, {
        method: "POST",
        body: JSON.stringify(payload),
      });
      state.currency = state.session.currency;
      byId("sale-currency").value = state.currency;
      byId("sale-currency").disabled = true;
      renderCart();
      closeDialog(byId("open-session-dialog"));
      setSessionState();
      updateCheckoutAvailability();
      showAlert("Caja abierta correctamente.", "success");
      byId("product-search").focus();
    } catch (error) {
      showAlert(error.message);
    } finally {
      setBusy(false);
    }
  }

  async function registerMovement(event) {
    event.preventDefault();
    if (!state.session) return;
    setBusy(true, "Registrando movimiento…");
    try {
      const result = await api(`/api/v1/pos/sessions/${state.session.id}/movements/`, {
        method: "POST",
        body: JSON.stringify({
          movement_type: byId("movement-type").value,
          amount: fixed(byId("movement-amount").value),
          reason_code: byId("movement-reason-code").value,
          description: byId("movement-description").value.trim(),
        }),
      });
      byId("cash-movement-form").reset();
      closeDialog(byId("cash-movement-dialog"));
      showAlert(`Movimiento registrado. Efectivo disponible en gaveta: ${currencySymbol()} ${result.drawer_cash_after}.`, "success");
    } catch (error) {
      showAlert(error.message);
    } finally {
      setBusy(false);
    }
  }

  function renderCashMovementHistory(summary) {
    const container = byId("cash-movement-history");
    const movements = summary?.movement_details || [];
    container.innerHTML = movements.length ? movements.map((item) => `
      <div class="pos-cash-ledger__row">
        <span><strong>${escapeHtml(item.movement_type_label)}</strong><small>${new Date(item.created_at).toLocaleString("es-PE")} · ${escapeHtml(item.description)}</small></span>
        <strong class="${["PAY_OUT", "WITHDRAWAL", "DEPOSIT"].includes(item.movement_type) ? "is-out" : "is-in"}">${["PAY_OUT", "WITHDRAWAL", "DEPOSIT"].includes(item.movement_type) ? "-" : "+"} ${currencySymbol()} ${escapeHtml(item.amount)}</strong>
      </div>`).join("") : '<div class="pos-no-results">Sin ingresos ni salidas registrados en esta sesión.</div>';
  }

  async function openCashMovementDialog() {
    if (!state.session) return;
    openDialog(byId("cash-movement-dialog"));
    byId("cash-movement-history").innerHTML = '<div class="pos-no-results">Cargando movimientos…</div>';
    try {
      renderCashMovementHistory(await api(`/api/v1/pos/sessions/${state.session.id}/summary/`));
      byId("movement-amount").focus();
    } catch (error) {
      byId("cash-movement-history").innerHTML = `<div class="pos-no-results">${escapeHtml(error.message)}</div>`;
    }
  }

  function renderCashCloseDetails(summary) {
    const payments = summary.payments || [];
    const sales = summary.sales || [];
    const movements = summary.movement_details || [];
    byId("cash-close-details").innerHTML = `
      <section><h3>Resumen por medio de pago</h3><div class="pos-cash-detail-table">
        ${payments.length ? payments.map((item) => `<div><span>${escapeHtml(item.name)} <small>${item.operations} operación(es)</small></span><strong>${currencySymbol()} ${escapeHtml(item.expected_amount)}</strong></div>`).join("") : `<div><span>Sin pagos registrados</span><strong>${currencySymbol()} 0.00</strong></div>`}
      </div></section>
      <section><h3>Ventas de la sesión</h3><div class="pos-cash-detail-list">
        ${sales.length ? sales.map((item) => `<div><span><strong>${escapeHtml(item.document)}</strong><small>${item.completed_at ? new Date(item.completed_at).toLocaleString("es-PE") : "Pendiente"} · ${escapeHtml(item.customer)}</small></span><strong>${escapeHtml(currencySymbol(item.currency))} ${escapeHtml(item.total)}</strong></div>`).join("") : '<div class="pos-no-results">Sin ventas en la sesión.</div>'}
      </div></section>
      <section><h3>Vales y movimientos de caja</h3><div class="pos-cash-detail-list">
        ${movements.length ? movements.map((item) => `<div><span><strong>${escapeHtml(item.movement_type === "PAY_IN" ? "Vale de ingreso" : item.movement_type === "PAY_OUT" ? "Vale de salida" : item.movement_type_label)}</strong><small>${new Date(item.created_at).toLocaleString("es-PE")} · ${escapeHtml(item.description)}</small></span><strong>${["PAY_OUT", "WITHDRAWAL", "DEPOSIT"].includes(item.movement_type) ? "-" : "+"} ${currencySymbol()} ${escapeHtml(item.amount)}</strong></div>`).join("") : '<div class="pos-no-results">Sin vales ni movimientos manuales.</div>'}
      </div></section>`;
  }

  function renderCashSummary(summary) {
    const transactions = summary.transactions || {};
    const session = summary.session || {};
    const openedAt = session.opened_at ? new Date(session.opened_at).toLocaleString("es-PE") : "—";
    const closedAt = session.closed_at ? new Date(session.closed_at).toLocaleString("es-PE") : "Caja activa";
    const warning = summary.can_close
      ? ""
      : `<div class="pos-cash-warning">Hay ${transactions.pending || 0} venta(s) o ${transactions.pending_invoices || 0} factura(s) pendientes.</div>`;
    byId("cash-close-summary").innerHTML = `
      <div class="pos-cash-summary__range"><span>Rango del cierre</span><strong>${escapeHtml(openedAt)} — ${escapeHtml(closedAt)}</strong></div>
      <div class="pos-cash-summary__metric"><span>Total cobrado</span><strong>${currencySymbol()} ${escapeHtml(summary.payment_total)}</strong><small>${transactions.completed || 0} venta(s)</small></div>
      <div class="pos-cash-summary__metric"><span>Vales de ingreso</span><strong>${currencySymbol()} ${escapeHtml(summary.cash_in)}</strong><small>Entradas manuales</small></div>
      <div class="pos-cash-summary__metric"><span>Vales de salida / retiros</span><strong>${currencySymbol()} ${escapeHtml(summary.cash_out)}</strong><small>Salidas de gaveta</small></div>
      <div class="pos-cash-summary__metric is-total"><span>Efectivo esperado</span><strong>${currencySymbol()} ${escapeHtml(summary.expected_cash_total)}</strong><small>Incluye fondo ${currencySymbol()} ${escapeHtml(summary.opening_total)}</small></div>
      <div><span>Ventas en efectivo</span><strong>${currencySymbol()} ${escapeHtml(summary.cash_sales)}</strong></div>
      <div><span>Otros medios</span><strong>${currencySymbol()} ${escapeHtml(summary.non_cash_sales)}</strong></div>
      <div><span>Devoluciones</span><strong>- ${currencySymbol()} ${escapeHtml(summary.refund_total)}</strong></div>
      ${warning}`;
    renderCashCloseDetails(summary);

    const nonCashPayments = (summary.payments || []).filter((item) => item.kind !== "CASH");
    byId("close-tender-counts").innerHTML = nonCashPayments.length
      ? `<h3>Conciliación de otros medios</h3>${nonCashPayments.map((item) => `
          <label class="pos-tender-row">
            <span><strong>${escapeHtml(item.name)}</strong><small>Esperado: ${currencySymbol()} ${escapeHtml(item.expected_amount)} · ${item.operations} operación(es)</small></span>
            <input type="number" step="0.01" value="${escapeHtml(item.counted_amount ?? item.expected_amount)}" data-tender-id="${item.means_of_payment_id}" data-expected-amount="${escapeHtml(item.expected_amount)}">
          </label>`).join("")}`
      : "";
    byId("close-session-submit").disabled = !summary.can_close;
    updateCashDifferencePreview();
    byId("counted-cash").value = fixed(summary.expected_cash_total);
    byId("next-opening-total").value = "0.00";
    byId("bank-deposit-total").value = "0.00";
    byId("bank-deposit-destination").value = "";
    updateCashAllocation(true);
  }

  async function prepareCashClose() {
    if (!state.session) return;
    openDialog(byId("close-session-dialog"));
    byId("cash-close-summary").innerHTML = "<span>Cargando resumen de caja…</span>";
    byId("close-session-submit").disabled = true;
    try {
      state.cashSummary = await api(`/api/v1/pos/sessions/${state.session.id}/summary/`);
      renderCashSummary(state.cashSummary);
      byId("counted-cash").focus();
    } catch (error) {
      closeDialog(byId("close-session-dialog"));
      showAlert(error.message);
    }
  }

  function renderCashCloseReport(summary, closed) {
    const paymentRows = (summary.payments || []).map((item) => `
      <div class="pos-receipt__row"><span>${escapeHtml(item.name)}</span><span>${currencySymbol()} ${escapeHtml(item.expected_amount)}</span></div>`).join("");
    byId("cash-close-report").innerHTML = `
      <div class="pos-receipt__header"><strong>${escapeHtml(state.register?.name || "Caja POS")}</strong><br><span>CIERRE DE CAJA</span></div>
      <div class="pos-receipt__row"><span>Apertura</span><span>${currencySymbol()} ${escapeHtml(summary.opening_total)}</span></div>
      <div class="pos-receipt__row"><span>Ingresos de caja</span><span>${currencySymbol()} ${escapeHtml(summary.cash_in)}</span></div>
      <div class="pos-receipt__row"><span>Salidas de caja</span><span>${currencySymbol()} ${escapeHtml(summary.cash_out)}</span></div>
      ${paymentRows}
      <div class="pos-receipt__row pos-receipt__total"><span>Efectivo esperado</span><span>${currencySymbol()} ${escapeHtml(closed.expected_cash_total)}</span></div>
      <div class="pos-receipt__row"><span>Efectivo contado</span><span>${currencySymbol()} ${escapeHtml(closed.counted_cash_total)}</span></div>
      <div class="pos-receipt__row"><strong>Diferencia</strong><strong>${currencySymbol()} ${escapeHtml(closed.cash_difference)}</strong></div>
      <div class="pos-receipt__row"><span>Queda en gaveta</span><span>${currencySymbol()} ${escapeHtml(closed.next_opening_total)}</span></div>
      <div class="pos-receipt__row"><span>Guardado en caja fuerte</span><span>${currencySymbol()} ${escapeHtml(closed.safe_deposit_total)}</span></div>
      <div class="pos-receipt__row"><span>Enviado al banco</span><span>${currencySymbol()} ${escapeHtml(closed.bank_deposit_total)}</span></div>
      ${number(closed.bank_deposit_total) > 0 ? `<div class="pos-receipt__row"><span>Destino banco</span><span>${escapeHtml(closed.bank_deposit_destination)}</span></div>` : ""}`;
  }

  async function closeCashSession(event) {
    event.preventDefault();
    if (!state.session) return;
    setBusy(true, "Cerrando caja…");
    try {
      const denominations = collectDenominations("closing-denominations");
      const tenderCounts = [...byId("close-tender-counts").querySelectorAll("[data-tender-id]")]
        .map((input) => ({
          means_of_payment_id: input.dataset.tenderId,
          counted_amount: fixed(input.value),
        }));
      const payload = {
        counted_cash_total: fixed(byId("counted-cash").value),
        tender_counts: tenderCounts,
        next_opening_total: fixed(byId("next-opening-total").value),
        safe_deposit_total: fixed(byId("safe-deposit-total").value),
        bank_deposit_total: fixed(byId("bank-deposit-total").value),
        bank_deposit_destination: byId("bank-deposit-destination").value.trim(),
        note: byId("closing-note").value.trim(),
      };
      if (denominations.length) payload.denominations = denominations;
      const closed = await api(`/api/v1/pos/sessions/${state.session.id}/close/`, {
        method: "POST",
        body: JSON.stringify(payload),
      });
      renderCashCloseReport(state.cashSummary, closed);
      state.session = null;
      state.cashSummary = null;
      closeDialog(byId("close-session-dialog"));
      setSessionState();
      openDialog(byId("cash-close-report-dialog"));
      showAlert(`Caja cerrada. Diferencia: ${currencySymbol()} ${closed.cash_difference}.`, "success");
    } catch (error) {
      showAlert(error.message);
    } finally {
      setBusy(false);
    }
  }

  function renderCreditCollections(records) {
    state.creditCollections = records;
    byId("credit-collection-results").innerHTML = records.length ? records.map((item) => `
      <button class="pos-search-result" type="button" data-collection-document="${item.sales_document_id}">
        <span><strong>${escapeHtml(item.document)}</strong><small>${escapeHtml(item.customer)} · Vence ${escapeHtml(item.due_date || "sin fecha")}</small></span>
        <span><small>Total ${escapeHtml(currencySymbol(item.currency))} ${escapeHtml(item.total)}</small><strong>Saldo ${escapeHtml(currencySymbol(item.currency))} ${escapeHtml(item.outstanding_total)}</strong></span>
      </button>`).join("") : '<div class="pos-no-results">No hay ventas a crédito pendientes.</div>';
  }

  async function loadCreditCollections() {
    if (!state.session) return;
    openDialog(byId("credit-collection-dialog"));
    byId("credit-collection-form").hidden = true;
    byId("credit-collection-results").innerHTML = '<div class="pos-no-results">Cargando cuentas pendientes…</div>';
    try {
      const search = byId("collection-search").value.trim();
      renderCreditCollections(await api(`${endpoints.collections}?search=${encodeURIComponent(search)}&cash_session_id=${encodeURIComponent(state.session.id)}`));
      byId("collection-search").focus();
    } catch (error) {
      byId("credit-collection-results").innerHTML = `<div class="pos-no-results">${escapeHtml(error.message)}</div>`;
    }
  }

  function selectCreditCollection(documentId) {
    const item = state.creditCollections.find((record) => record.sales_document_id === documentId);
    if (!item) return;
    byId("collection-document-id").value = item.sales_document_id;
    byId("collection-currency-symbol").textContent = currencySymbol(item.currency);
    byId("collection-amount").value = item.outstanding_total;
    byId("collection-amount").max = item.outstanding_total;
    byId("collection-reference").value = "";
    byId("collection-selected-sale").innerHTML = `<div><span>${escapeHtml(item.document)} · ${escapeHtml(item.customer)}</span><strong>Saldo ${escapeHtml(currencySymbol(item.currency))} ${escapeHtml(item.outstanding_total)}</strong></div>`;
    byId("collection-means").innerHTML = state.means.map((means) => `<option value="${means.id}">${escapeHtml(means.name)}</option>`).join("");
    byId("credit-collection-form").hidden = false;
    byId("collection-amount").focus();
  }

  async function submitCreditCollection(event) {
    event.preventDefault();
    const amount = number(byId("collection-amount").value);
    const max = number(byId("collection-amount").max);
    if (amount <= 0 || amount > max) return showAlert("El importe debe ser mayor que cero y no superar el saldo.");
    setBusy(true, "Registrando cobranza…");
    try {
      const result = await api(endpoints.collections, {
        method: "POST",
        body: JSON.stringify({
          sales_document_id: byId("collection-document-id").value,
          cash_session_id: state.session.id,
          means_of_payment_id: byId("collection-means").value,
          amount: fixed(amount),
          received_amount: fixed(amount),
          operation_reference: byId("collection-reference").value.trim(),
          idempotency_key: uuid(),
        }),
      });
      byId("credit-collection-form").hidden = true;
      showAlert(`Cobranza registrada. Saldo pendiente: ${currencySymbol()} ${result.outstanding_total}.`, "success");
      await loadCreditCollections();
    } catch (error) {
      showAlert(error.message);
    } finally {
      setBusy(false);
    }
  }

  async function createCustomer(event) {
    event.preventDefault();
    setBusy(true, "Guardando cliente…");
    try {
      const customer = await api(endpoints.customers, {
        method: "POST",
        body: JSON.stringify({
          document_type: byId("customer-document-type").value,
          document_number: byId("customer-document-number").value.trim(),
          legal_name: byId("customer-legal-name").value.trim(),
          address: byId("customer-address-input").value.trim(),
          phone: byId("customer-phone").value.trim(),
          email: byId("customer-email").value.trim(),
        }),
      });
      selectCustomer(customer);
      byId("customer-form").reset();
      closeDialog(byId("customer-dialog"));
      showAlert(customer.created ? "Cliente creado correctamente." : "El cliente ya estaba registrado.", "success");
    } catch (error) {
      showAlert(error.message);
    } finally {
      setBusy(false);
    }
  }

  async function loadInvoiceableTickets() {
    if (!state.selectedCustomer || state.selectedCustomer.document_number?.length !== 11) {
      byId("invoiceable-tickets").innerHTML = '<div class="pos-no-results">Seleccione un cliente con RUC para consolidar sus tickets.</div>';
      byId("consolidate-button").disabled = true;
      openDialog(byId("consolidation-dialog"));
      return;
    }
    openDialog(byId("consolidation-dialog"));
    byId("invoiceable-tickets").innerHTML = '<div class="pos-no-results">Buscando tickets…</div>';
    try {
      const params = new URLSearchParams({ customer_id: state.selectedCustomer.id, date: localDate() });
      state.invoiceableTickets = await api(`${endpoints.invoiceable}?${params}`);
      byId("consolidation-help").textContent = `${state.selectedCustomer.legal_name} · ${localDate()}`;
      byId("invoiceable-tickets").innerHTML = state.invoiceableTickets.length
        ? state.invoiceableTickets.map((ticket) => `
          <label class="pos-ticket-row">
            <input type="checkbox" value="${ticket.sales_document_id}" data-ticket-total="${ticket.total}">
            <span><strong>${escapeHtml(ticket.ticket_code)}</strong><small>${new Date(ticket.completed_at).toLocaleTimeString("es-PE", { hour: "2-digit", minute: "2-digit" })}</small></span>
            <strong>${escapeHtml(currencySymbol(ticket.currency))} ${escapeHtml(ticket.total)}</strong>
          </label>`).join("")
        : '<div class="pos-no-results">No hay Notas de Venta pendientes para este cliente hoy.</div>';
      updateConsolidationTotal();
    } catch (error) {
      byId("invoiceable-tickets").innerHTML = `<div class="pos-no-results">${escapeHtml(error.message)}</div>`;
    }
  }

  function selectedTicketIds() {
    return [...byId("invoiceable-tickets").querySelectorAll("input:checked")].map((input) => input.value);
  }

  function updateConsolidationTotal() {
    const checked = [...byId("invoiceable-tickets").querySelectorAll("input:checked")];
    const total = checked.reduce((sum, input) => sum + number(input.dataset.ticketTotal), 0);
    byId("consolidation-total").textContent = fixed(total);
    byId("consolidate-button").disabled = !checked.length || !byId("invoice-series").value;
  }

  async function consolidateTickets(event) {
    event.preventDefault();
    const sourceIds = selectedTicketIds();
    if (!sourceIds.length) return;
    setBusy(true, "Emitiendo factura consolidada…");
    try {
      await api(endpoints.invoiceRequest, {
        method: "POST",
        body: JSON.stringify({ source_document_ids: sourceIds }),
      });
      const invoice = await api(endpoints.consolidate, {
        method: "POST",
        body: JSON.stringify({
          source_document_ids: sourceIds,
          invoice_series_id: byId("invoice-series").value,
        }),
      });
      closeDialog(byId("consolidation-dialog"));
      showAlert(`Factura ${invoice.series}-${invoice.number} emitida por ${currencySymbol(invoice.currency)} ${invoice.total}.`, "success");
      await loadBootstrap(state.register.id);
    } catch (error) {
      showAlert(error.message);
    } finally {
      setBusy(false);
    }
  }

  byId("dismiss-alert").addEventListener("click", hideAlert);
  byId("pos-register").addEventListener("change", async (event) => {
    if (state.cart.size && !confirm("La venta actual se limpiará al cambiar de caja. ¿Continuar?")) {
      event.target.value = state.register?.id || "";
      return;
    }
    state.cart.clear();
    markSaleDirty();
    await loadBootstrap(event.target.value);
    renderCart();
  });
  document.querySelectorAll("[data-document-type]").forEach((button) => {
    button.addEventListener("click", () => setDocumentType(button.dataset.documentType));
  });
  document.querySelectorAll("[data-payment-condition]").forEach((button) => {
    button.addEventListener("click", () => setPaymentCondition(button.dataset.paymentCondition));
  });
  byId("document-series").addEventListener("change", markSaleDirty);
  byId("payment-method").addEventListener("change", () => {
    markSaleDirty();
    if (state.paymentCondition === "CREDIT") byId("credit-due-date").value = defaultDueDate();
  });
  byId("credit-due-date").addEventListener("change", markSaleDirty);
  byId("sale-notes").addEventListener("input", markSaleDirty);
  byId("exchange-rate").addEventListener("input", markSaleDirty);
  byId("product-search").addEventListener("input", () => {
    clearTimeout(productSearchTimer);
    productSearchTimer = setTimeout(
      state.productSearchMode === "CATALOG" ? loadCatalog : searchProducts,
      220,
    );
  });
  byId("product-search").addEventListener("keydown", (event) => {
    if (state.productSearchMode === "SEARCH" && event.key === "ArrowDown" && state.productResults.length) {
      event.preventDefault();
      moveProductSelection(1);
    } else if (state.productSearchMode === "SEARCH" && event.key === "ArrowUp" && state.productResults.length) {
      event.preventDefault();
      moveProductSelection(-1);
    } else if (event.key === "Enter" && state.productSearchMode === "CATALOG" && state.catalogProducts.length === 1) {
      event.preventDefault();
      addProduct(state.catalogProducts[0]);
    } else if (event.key === "Enter" && state.productResults.length) {
      event.preventDefault();
      addProduct(state.productResults[Math.max(state.activeProductIndex, 0)]);
    } else if (event.key === "Escape") {
      hideProductResults();
    }
  });
  byId("product-results").addEventListener("click", (event) => {
    if (event.target.closest("[data-create-manual-line]")) {
      addManualLine();
      return;
    }
    if (event.target.closest("[data-create-product]")) {
      openQuickProduct();
      return;
    }
    const button = event.target.closest("[data-product-id]");
    if (!button) return;
    const product = state.productResults.find((item) => item.id === button.dataset.productId);
    if (product) addProduct(product);
  });
  byId("product-catalog").addEventListener("click", (event) => {
    const button = event.target.closest("[data-catalog-product-id]");
    if (!button) return;
    const product = state.catalogProducts.find((item) => item.id === button.dataset.catalogProductId);
    if (product) addProduct(product);
  });
  byId("product-catalog").addEventListener("keydown", (event) => {
    if (!["ArrowRight", "ArrowDown", "ArrowLeft", "ArrowUp"].includes(event.key)) return;
    const cards = [...byId("product-catalog").querySelectorAll("[data-catalog-product-id]:not(:disabled)")];
    const current = cards.indexOf(document.activeElement);
    if (!cards.length || current < 0) return;
    event.preventDefault();
    const direction = ["ArrowRight", "ArrowDown"].includes(event.key) ? 1 : -1;
    cards[(current + direction + cards.length) % cards.length].focus();
  });
  byId("category-filters").addEventListener("click", async (event) => {
    const button = event.target.closest("[data-category-id]");
    if (!button) return;
    state.selectedCategory = button.dataset.categoryId;
    renderCategoryFilters();
    await loadCatalog(byId("product-search").value.trim());
  });
  byId("refresh-catalog").addEventListener("click", loadCatalog);
  document.addEventListener("click", (event) => {
    if (!event.target.closest(".pos-search-wrap")) hideProductResults();
    if (!event.target.closest(".pos-customer-section")) byId("customer-results").hidden = true;
  });
  document.addEventListener("keydown", (event) => {
    const openDialogs = [...document.querySelectorAll("dialog[open]")];
    if (event.key === "Escape" && openDialogs.length) {
      event.preventDefault();
      const dialog = openDialogs.at(-1);
      if (!(dialog.id === "open-session-dialog" && !state.session)) closeDialog(dialog);
      return;
    }
    if (event.key === "F2") {
      event.preventDefault();
      byId("product-search").focus();
      byId("product-search").select();
    } else if (event.key === "F4" && !openDialogs.length) {
      event.preventDefault();
      if (state.selectedCustomer) selectCustomer(null);
      byId("customer-search").focus();
      byId("customer-search").select();
    } else if (event.key === "F8" && !openDialogs.length) {
      event.preventDefault();
      if (!byId("checkout-button").disabled) prepareCheckoutReview();
      else showAlert(checkoutProblem() || "No puede cobrar esta venta.");
    } else if (event.key === "F7" && !openDialogs.length) {
      event.preventDefault();
      if (!byId("save-draft-button").disabled) saveDraft();
      else showAlert(draftProblem() || "No puede guardar este borrador.");
    } else if (event.key === "F9" && !openDialogs.length && !byId("quick-cash-movement").disabled) {
      event.preventDefault();
      openCashMovementDialog();
    } else if (event.key === "F10" && !openDialogs.length && !byId("quick-sales-history").disabled) {
      event.preventDefault();
      loadRecentSales();
    } else if (event.altKey && ["1", "2", "3"].includes(event.key) && !openDialogs.length) {
      event.preventDefault();
      setDocumentType({ "1": "NV", "2": "03", "3": "01" }[event.key]);
    } else if (event.altKey && event.key.toLowerCase() === "l" && !openDialogs.length) {
      event.preventDefault();
      addManualLine();
    } else if (event.altKey && ["q", "p", "g", "m"].includes(event.key.toLowerCase()) && !openDialogs.length) {
      event.preventDefault();
      if (event.key.toLowerCase() === "g") {
        byId("global-discount").focus();
        byId("global-discount").select();
      } else if (event.key.toLowerCase() === "m") {
        openLineMemo();
      } else if (state.activeCartLineId) {
        const action = event.key.toLowerCase() === "q" ? "quantity" : "price";
        const input = byId("cart-lines").querySelector(`[data-line-id="${state.activeCartLineId}"] [data-action="${action}"]`);
        input?.focus();
        input?.select();
      }
    } else if (["+", "-", "Delete"].includes(event.key) && !openDialogs.length && state.activeCartLineId && !event.target.matches("input, textarea, select")) {
      event.preventDefault();
      const line = state.cart.get(state.activeCartLineId);
      if (!line) return;
      if (event.key === "+") line.quantity += 1;
      if (event.key === "-") line.quantity = Math.max(0.001, line.quantity - 1);
      if (event.key === "Delete") {
        state.cart.delete(line.id);
        state.activeCartLineId = state.cart.keys().next().value || null;
      }
      markSaleDirty();
      renderCart();
    }
  });
  byId("cart-lines").addEventListener("click", (event) => {
    const row = event.target.closest("[data-line-id]");
    const action = event.target.closest("[data-action]")?.dataset.action;
    if (!row) return;
    state.activeCartLineId = row.dataset.lineId;
    byId("cart-lines").querySelectorAll("tr").forEach((item) => item.classList.toggle("is-selected", item === row));
    if (!action) return;
    if (action === "memo") {
      openLineMemo(row.dataset.lineId);
      return;
    }
    if (action === "prices" || action === "stock") {
      openProductCommercial(row.dataset.lineId, action);
      return;
    }
    if (!["increase", "decrease", "remove"].includes(action)) return;
    const line = state.cart.get(row.dataset.lineId);
    if (!line) return;
    if (action === "increase") line.quantity += 1;
    if (action === "decrease") line.quantity = Math.max(0.001, line.quantity - 1);
    if (action === "remove") state.cart.delete(line.id);
    markSaleDirty();
    renderCart();
  });
  byId("cart-lines").addEventListener("change", (event) => {
    const row = event.target.closest("[data-line-id]");
    const action = event.target.dataset.action;
    if (!row || !action) return;
    const line = state.cart.get(row.dataset.lineId);
    if (!line) return;
    if (action === "unit") {
      const unit = line.units.find((item) => item.id === event.target.value);
      if (unit && unit.unit_price !== null) {
        line.unitId = unit.id;
        line.unit = unit.code;
        line.conversionFactor = Math.max(number(unit.conversion_factor), 0.000001);
        line.stock = line.baseStock / line.conversionFactor;
        line.netPrice = number(unit.unit_price);
        line.originalNetPrice = number(unit.unit_price);
        line.priceChanged = false;
        line.discount = 0;
      }
    }
    if (action === "quantity") line.quantity = Math.max(number(event.target.value), 0.001);
    if (action === "discount") line.discount = Math.max(number(event.target.value), 0);
    if (action === "description" && line.manual) {
      line.name = event.target.value.trim().slice(0, 500) || "Producto o servicio sin registrar";
    }
    if (action === "code" && line.manual) {
      line.sku = event.target.value.trim().slice(0, 100) || "SIN CODIGO";
    }
    if (action === "tax" && line.manual) {
      const gross = grossUnitPrice(line);
      line.taxType = event.target.value;
      line.igvRate = number(state.taxRates[line.taxType] || 0);
      line.netPrice = number((line.taxType === "10" ? gross / (1 + line.igvRate / 100) : gross).toFixed(6));
      line.originalNetPrice = line.netPrice;
    }
    if (action === "price" && (line.manual || hasPermission("change.pos.price"))) {
      const gross = Math.max(number(event.target.value), 0);
      line.netPrice = number((
        line.taxType === "10" ? gross / (1 + line.igvRate / 100) : gross
      ).toFixed(6));
      line.priceChanged = Math.abs(line.netPrice - line.originalNetPrice) > 0.0000005;
    }
    markSaleDirty();
    renderCart();
  });
  byId("cart-lines").addEventListener("keydown", (event) => {
    if (event.key === "Enter" && ["description", "code", "quantity", "price", "discount"].includes(event.target.dataset.action)) {
      event.preventDefault();
      event.target.blur();
    }
  });
  byId("clear-cart").addEventListener("click", () => {
    if (state.cart.size && confirm("¿Quitar todos los productos de la venta?")) {
      state.cart.clear();
      markSaleDirty();
      renderCart();
    }
  });
  byId("global-discount").addEventListener("change", (event) => {
    state.globalDiscount = Math.max(number(event.target.value), 0);
    markSaleDirty();
    updateTotals();
  });
  byId("line-memo-text").addEventListener("input", (event) => {
    byId("line-memo-count").textContent = `${event.target.value.length}/500`;
  });
  byId("line-memo-form").addEventListener("submit", saveLineMemo);
  byId("quick-product-form").addEventListener("submit", createQuickProduct);
  byId("add-manual-line").addEventListener("click", addManualLine);
  byId("quick-product-tax").addEventListener("change", (event) => {
    const taxed = event.target.value === "10";
    byId("quick-product-includes-tax").disabled = !taxed;
    if (!taxed) byId("quick-product-includes-tax").checked = false;
  });
  byId("add-payment").addEventListener("click", () => {
    const usedMeans = new Set(state.payments.map((payment) => payment.meansId));
    const means = state.means.find((item) => item.kind !== "CASH" && !usedMeans.has(item.id))
      || state.means.find((item) => !usedMeans.has(item.id))
      || defaultMeans();
    if (!means) return;
    const balance = Math.max(totals().total - paymentTotal(), 0);
    state.payments.push({
      key: ++state.paymentSequence,
      meansId: means.id,
      amount: balance,
      received: balance,
      reference: "",
      automatic: false,
    });
    markSaleDirty();
    state.payments.forEach((payment) => { payment.automatic = false; });
    renderPayments();
  });
  byId("payment-lines").addEventListener("input", (event) => {
    const row = event.target.closest("[data-payment-key]");
    if (!row) return;
    const payment = state.payments.find((item) => item.key === number(row.dataset.paymentKey));
    if (!payment) return;
    const action = event.target.dataset.paymentAction;
    if (action === "amount") payment.amount = Math.max(number(event.target.value), 0);
    if (action === "received") payment.received = Math.max(number(event.target.value), 0);
    if (action === "reference") {
      payment.reference = event.target.value;
      const referenceField = event.target.closest(".pos-payment-reference");
      const missingReference = !payment.reference.trim();
      referenceField?.classList.toggle("has-warning", missingReference);
      event.target.classList.toggle("is-warning", missingReference);
      const warning = referenceField?.querySelector(".pos-payment-reference-warning");
      if (warning) warning.hidden = !missingReference;
    }
    payment.automatic = false;
    markSaleDirty();
    refreshPaymentCalculations();
    updateCheckoutAvailability();
  });
  byId("payment-lines").addEventListener("change", (event) => {
    const row = event.target.closest("[data-payment-key]");
    if (!row) return;
    const payment = state.payments.find((item) => item.key === number(row.dataset.paymentKey));
    if (!payment) return;
    if (event.target.dataset.paymentAction === "means") {
      const previousMeans = state.means.find((item) => item.id === payment.meansId);
      payment.meansId = event.target.value;
      const nextMeans = state.means.find((item) => item.id === payment.meansId);
      if (previousMeans?.kind === "CASH" && nextMeans?.kind !== "CASH") payment.amount = payment.received;
      if (previousMeans?.kind !== "CASH" && nextMeans?.kind === "CASH") payment.received = payment.amount;
      payment.reference = "";
      markSaleDirty();
      renderPayments();
    }
  });
  byId("payment-lines").addEventListener("click", (event) => {
    const button = event.target.closest('[data-payment-action="remove"]');
    const row = event.target.closest("[data-payment-key]");
    if (
      !button
      || !row
      || (state.paymentCondition === "CASH" && state.payments.length === 1)
    ) return;
    state.payments = state.payments.filter((item) => item.key !== number(row.dataset.paymentKey));
    markSaleDirty();
    renderPayments();
  });
  byId("customer-search").addEventListener("input", () => {
    clearTimeout(customerSearchTimer);
    customerSearchTimer = setTimeout(searchCustomers, 250);
  });
  byId("customer-search").addEventListener("keydown", (event) => {
    if (!["ArrowDown", "ArrowUp", "Enter", "Escape"].includes(event.key)) return;
    if (event.key === "Escape") {
      byId("customer-results").hidden = true;
      return;
    }
    if (!state.customerResults.length) return;
    event.preventDefault();
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      const direction = event.key === "ArrowDown" ? 1 : -1;
      state.activeCustomerIndex = (
        state.activeCustomerIndex + direction + state.customerResults.length
      ) % state.customerResults.length;
      byId("customer-results").querySelectorAll("[data-customer-id]").forEach((item, index) => {
        const active = index === state.activeCustomerIndex;
        item.classList.toggle("is-active", active);
        item.setAttribute("aria-selected", active ? "true" : "false");
        if (active) item.scrollIntoView({ block: "nearest" });
      });
    } else if (event.key === "Enter") {
      selectCustomer(state.customerResults[Math.max(state.activeCustomerIndex, 0)]);
    }
  });
  byId("customer-results").addEventListener("click", (event) => {
    const button = event.target.closest("[data-customer-id]");
    if (!button) return;
    selectCustomer(state.customerResults.find((item) => item.id === button.dataset.customerId));
  });
  byId("clear-customer").addEventListener("click", () => selectCustomer(null));
  byId("new-customer").addEventListener("click", () => openDialog(byId("customer-dialog")));
  byId("sale-currency").addEventListener("change", (event) => {
    if (state.cart.size && !confirm("Cambiar la moneda limpiará los productos y pagos. ¿Continuar?")) {
      event.target.value = state.currency;
      return;
    }
    state.currency = event.target.value;
    state.cart.clear();
    markSaleDirty();
    byId("exchange-rate-wrap").hidden = state.currency === "PEN";
    ensureDefaultPayment(true);
    renderCart();
    if (state.productSearchMode === "CATALOG") loadCatalog();
  });
  byId("sale-price-list").addEventListener("change", async (event) => {
    const previous = state.selectedPriceList || "";
    setBusy(true, "Actualizando precios…");
    try {
      await repriceCart(event.target.value || null);
      showAlert("Lista de precios actualizada sin modificar cantidades.", "success");
    } catch (error) {
      event.target.value = previous;
      showAlert(error.message);
    } finally {
      setBusy(false);
    }
  });
  byId("save-draft-button").addEventListener("click", saveDraft);
  byId("discard-draft-button").addEventListener("click", discardDraft);
  byId("checkout-button").addEventListener("click", prepareCheckoutReview);
  byId("checkout-review-form").addEventListener("submit", (event) => {
    event.preventDefault();
    checkout();
  });
  byId("mobile-checkout-button").addEventListener("click", () => document.body.classList.add("pos-checkout-open"));
  byId("close-mobile-checkout").addEventListener("click", () => document.body.classList.remove("pos-checkout-open"));
  byId("open-session-form").addEventListener("submit", openCashSession);
  byId("opening-currency").addEventListener("change", (event) => {
    byId("opening-currency-symbol").textContent = currencySymbol(event.target.value);
    byId("opening-total").value = fixed(state.suggestedOpeningTotals[event.target.value] || 0);
    renderDenominations("opening-denominations");
  });
  byId("open-session-dialog").addEventListener("cancel", (event) => {
    if (!state.session) event.preventDefault();
  });
  byId("open-movement").addEventListener("click", openCashMovementDialog);
  byId("cash-movement-form").addEventListener("submit", registerMovement);
  byId("movement-type").addEventListener("change", (event) => {
    if (event.target.value === "WITHDRAWAL") byId("movement-reason-code").value = "SAFE_WITHDRAWAL";
    if (event.target.value === "DEPOSIT") byId("movement-reason-code").value = "BANK_DEPOSIT";
  });
  byId("open-close-session").addEventListener("click", prepareCashClose);
  byId("close-session-form").addEventListener("submit", closeCashSession);
  byId("counted-cash").addEventListener("input", () => { updateCashDifferencePreview(); updateCashAllocation(true); });
  byId("next-opening-total").addEventListener("input", () => updateCashAllocation(true));
  byId("bank-deposit-total").addEventListener("input", () => updateCashAllocation(true));
  byId("safe-deposit-total").addEventListener("input", () => updateCashAllocation(false));
  byId("close-tender-counts").addEventListener("input", updateCashDifferencePreview);
  byId("opening-denominations").addEventListener("input", () => {
    const total = denominationTotal("opening-denominations");
    if (total > 0) byId("opening-total").value = fixed(total);
  });
  byId("closing-denominations").addEventListener("input", () => {
    const total = denominationTotal("closing-denominations");
    if (total > 0) byId("counted-cash").value = fixed(total);
    updateCashDifferencePreview();
    updateCashAllocation(true);
  });
  byId("customer-form").addEventListener("submit", createCustomer);
  byId("open-consolidation").addEventListener("click", loadInvoiceableTickets);
  byId("open-reprints").addEventListener("click", loadRecentSales);
  byId("quick-sales-history").addEventListener("click", loadRecentSales);
  byId("recent-sales-scope").addEventListener("change", (event) => {
    byId("recent-sales-date").disabled = event.target.value !== "day";
    loadRecentSales();
  });
  byId("recent-sales-date").addEventListener("change", loadRecentSales);
  byId("open-collections").addEventListener("click", loadCreditCollections);
  byId("quick-collections").addEventListener("click", loadCreditCollections);
  byId("credit-collection-results").addEventListener("click", (event) => {
    const button = event.target.closest("[data-collection-document]");
    if (button) selectCreditCollection(button.dataset.collectionDocument);
  });
  byId("credit-collection-form").addEventListener("submit", submitCreditCollection);
  byId("collection-search").addEventListener("change", loadCreditCollections);
  document.querySelector("[data-cancel-collection]").addEventListener("click", () => {
    byId("credit-collection-form").hidden = true;
  });
  byId("quick-cash-movement").addEventListener("click", openCashMovementDialog);
  byId("quick-close-session").addEventListener("click", prepareCashClose);
  byId("recent-sales").addEventListener("click", (event) => {
    const draftButton = event.target.closest("[data-load-draft-id]");
    if (draftButton) {
      loadDraft(draftButton.dataset.loadDraftId);
      return;
    }
    const button = event.target.closest("[data-reprint-id]");
    if (button) prepareReprint(button.dataset.reprintId);
  });
  byId("invoiceable-tickets").addEventListener("change", updateConsolidationTotal);
  byId("invoice-series").addEventListener("change", updateConsolidationTotal);
  byId("consolidation-form").addEventListener("submit", consolidateTickets);
  document.querySelectorAll("[data-close-dialog]").forEach((button) => {
    button.addEventListener("click", () => closeDialog(button.closest("dialog")));
  });
  byId("new-sale-button").addEventListener("click", () => {
    closeDialog(byId("success-dialog"));
    byId("product-search").focus();
  });
  byId("return-sale-button").addEventListener("click", openReturnDialog);
  byId("return-form").addEventListener("submit", submitReturn);
  byId("debit-note-button").addEventListener("click", openDebitNoteDialog);
  byId("debit-note-form").addEventListener("submit", submitDebitNote);
  byId("receipt-width").addEventListener("change", (event) => setReceiptWidth(event.target.value));
  byId("print-receipt-button").addEventListener("click", () => window.print());

  const saleNotes = document.querySelector(".pos-notes");
  const compactSaleNotes = window.matchMedia("(max-width: 820px)");
  const syncSaleNotesLayout = (event) => {
    saleNotes.open = !event.matches;
  };
  syncSaleNotesLayout(compactSaleNotes);
  compactSaleNotes.addEventListener?.("change", syncSaleNotesLayout);

  renderDenominations("opening-denominations");
  renderDenominations("closing-denominations");
  byId("recent-sales-date").value = localDate();
  renderCart();
  setReceiptWidth("80");
  loadBootstrap();
})();

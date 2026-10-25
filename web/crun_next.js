import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

const ROOT = "/crun-next";
const OPEN_SETTING = "CRUNNext.Workspace.Open";
const PROVIDERS = ["kling", "bytedance", "vidu"];
let workspace = null;
let latestStatus = null;
let localNonce = "";
const settingsViews = new Map();

export function connectionText(status) {
    if (!status?.configured) return "No API key saved";
    const state = status.validation_state || "saved";
    const checked = status.checked_at ? ` · last check ${new Date(status.checked_at * 1000).toLocaleString()}` : " · not checked";
    const labels = { connected: "Previously verified", invalid: "Saved key rejected", unreachable: "Key saved · provider unreachable", error: "Key saved · check failed", saved: "Key saved" };
    return `${labels[state] || "Key saved"}${checked}`;
}

export function modelAvailabilityText(entry, checkedAt = null) {
    let label;
    if (entry.availability === "listed_in_authenticated_llm_catalog") {
        label = "Listed in last authenticated LLM inventory · execution not tested";
    } else if (entry.availability === "not_listed_in_current_llm_catalog") {
        label = "Not listed in last authenticated LLM inventory · not an execution failure";
    } else {
        return "Documentation only · account availability not verified";
    }
    if (checkedAt) {
        const date = new Date(typeof checkedAt === "number" ? checkedAt * 1000 : checkedAt);
        if (!Number.isNaN(date.getTime())) label += ` · checked ${date.toLocaleString()}`;
    }
    return label;
}

function applyLocalStatus(status) {
    latestStatus = status;
    if (status.nonce) localNonce = status.nonce;
    for (const refresh of settingsViews.values()) refresh(status);
}

async function localApiRequest(path, { method = "GET", body, useNonce = true, signal } = {}) {
    if (useNonce && !localNonce) await readPublicStatus(signal);
    const headers = { Accept: "application/json" };
    if (useNonce) headers["X-CRUN-Nonce"] = localNonce;
    if (body !== undefined) headers["Content-Type"] = "application/json";
    let response;
    try {
        response = await api.fetchApi(`${ROOT}${path}`, {
            method, headers, body: body === undefined ? undefined : JSON.stringify(body),
            cache: "no-store", signal,
        });
    } catch (error) {
        if (error?.name === "AbortError") throw error;
        throw new Error("Cannot reach the local CRUN Next extension. Check installation and restart ComfyUI.");
    }
    let payload;
    try { payload = await response.json(); }
    catch { throw new Error("The local CRUN Next extension returned an unreadable response."); }
    if (!response.ok || !payload.ok) {
        throw new Error(typeof payload.error === "string" ? payload.error.slice(0, 400) : "The operation could not be completed.");
    }
    return payload;
}

async function readPublicStatus(signal) {
    const status = await localApiRequest("/status", { useNonce: false, signal });
    applyLocalStatus(status);
    return status;
}

async function checkSavedConnection() {
    try { return await localApiRequest("/connection", { method: "POST", body: {} }); }
    finally { await readPublicStatus().catch(() => {}); }
}

export function formatCredits(value) {
    if ((typeof value !== "number" && typeof value !== "string") || value === "") return "Not available";
    const amount = Number(value);
    return Number.isFinite(amount) && amount >= 0
        ? `${new Intl.NumberFormat("en", { maximumFractionDigits: 4 }).format(amount)} credits`
        : "Not available";
}

export function formatEffectCredits(value) {
    if (!Array.isArray(value)) return formatCredits(value);
    if (!value.length) return "Not available";
    return value.map(tier => `${String(tier.resolution || "Option")}: ${formatCredits(tier.credits)}`).join(" · ");
}

export function safeRemoteUrl(value) {
    try {
        const url = new URL(String(value));
        if (url.protocol !== "https:" || url.username || url.password) return null;
        const host = url.hostname.toLowerCase();
        if (host === "localhost" || host.startsWith("[") || /^(127\.|10\.|192\.168\.|169\.254\.|0\.)/.test(host)) return null;
        if (/^172\.(1[6-9]|2\d|3[01])\./.test(host)) return null;
        return url.href;
    } catch {
        return null;
    }
}

export function filterEffects(cards, query) {
    const needle = String(query || "").trim().toLowerCase();
    return (Array.isArray(cards) ? cards : []).filter(card =>
        [card?.name, card?.id, card?.category, card?.provider]
            .some(value => String(value || "").toLowerCase().includes(needle)));
}

export function effectPlan(card) {
    return {
        schema_version: "crun-next.effect-plan.v1",
        provider: String(card.provider),
        template_id: String(card.id),
        name: String(card.name || card.id),
        required_images: Number.isInteger(card.required_images) ? card.required_images : null,
        inputs: { image_urls: [], options: {} },
        execution: "prepare_only",
        execution_enabled: false,
        note: "Preparation only. Validate the template-specific schema and image slots before enabling paid execution.",
    };
}

function node(tag, className, text) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined) element.textContent = String(text);
    return element;
}

function button(text, action, className = "crun-button") {
    const element = node("button", className, text);
    element.type = "button";
    element.addEventListener("click", action);
    return element;
}

function link(text, url) {
    const element = node("a", "crun-link", text);
    const safe = safeRemoteUrl(url);
    if (safe) {
        element.href = safe;
        element.target = "_blank";
        element.rel = "noopener noreferrer";
        element.referrerPolicy = "no-referrer";
    }
    return element;
}

function installStyles() {
    if (document.getElementById("crun-next-styles")) return;
    const style = node("link");
    style.id = "crun-next-styles";
    style.rel = "stylesheet";
    style.href = new URL("./crun_next.css", import.meta.url).href;
    document.head.append(style);
}

export function openCrunWorkspace(initialTab = "connection") {
    if (workspace) {
        workspace.selectTab(initialTab);
        workspace.dialog.focus();
        return;
    }
    installStyles();
    const previouslyFocused = document.activeElement;
    const controller = new AbortController();
    const dialog = node("dialog", "crun-workspace");
    dialog.setAttribute("aria-labelledby", "crun-workspace-title");
    dialog.setAttribute("aria-describedby", "crun-workspace-description");
    dialog.tabIndex = -1;
    let currentStatus = null;
    let activeTab = initialTab;
    let currentProvider = "kling";
    const catalogs = new Map();
    const pendingProviders = new Set();
    let tools = null;
    let toolsPending = false;
    const header = node("header", "crun-header");
    const headingGroup = node("div");
    headingGroup.append(node("span", "crun-eyebrow", "INDEPENDENT COMFYUI INTEGRATION"));
    const title = node("h2", "", "CRUN NEXT");
    title.id = "crun-workspace-title";
    const description = node("p", "crun-subtitle", "Your creative tools, one focused workspace.");
    description.id = "crun-workspace-description";
    headingGroup.append(title, description);
    const close = button("Close", closeWorkspace, "crun-button crun-button-quiet");
    close.setAttribute("aria-label", "Close CRUN Next workspace");
    header.append(headingGroup, close);
    const notice = node("div", "crun-notice", "This workspace browses and prepares. Paid generation is only available through an explicitly enabled execution node.");
    const tabs = node("div", "crun-tabs");
    tabs.setAttribute("role", "tablist");
    tabs.setAttribute("aria-label", "CRUN workspace sections");
    const tabButtons = new Map();
    const panels = new Map();
    const content = node("div", "crun-content");
    const feedback = node("p", "crun-feedback");
    feedback.setAttribute("role", "status");
    feedback.setAttribute("aria-live", "polite");
    for (const [id, label] of [["connection", "Connection"], ["models", "Models"], ["effects", "AI Effects"], ["tools", "AI Tools"]]) {
        const tabButton = button(label, () => selectTab(id), "crun-tab");
        tabButton.id = `crun-tab-${id}`;
        tabButton.setAttribute("role", "tab");
        tabButton.setAttribute("aria-controls", `crun-panel-${id}`);
        const panel = node("section", "crun-panel");
        panel.id = `crun-panel-${id}`;
        panel.setAttribute("role", "tabpanel");
        panel.setAttribute("aria-labelledby", tabButton.id);
        tabButtons.set(id, tabButton);
        panels.set(id, panel);
        tabs.append(tabButton);
        content.append(panel);
    }
    const footer = node("footer", "crun-footer");
    footer.append(node("span", "", "Unofficial. Not affiliated with or endorsed by CRUN."), link("API documentation ↗", "https://docs.crun.ai/"));
    dialog.append(header, notice, tabs, content, feedback, footer);
    document.body.append(dialog);

    function announce(message, isError = false) {
        feedback.textContent = message;
        feedback.classList.toggle("crun-error", isError);
    }

    async function localRequest(path, options = {}) {
        return localApiRequest(path, { ...options, signal: controller.signal });
    }

    async function readStatus() {
        const status = await readPublicStatus(controller.signal);
        currentStatus = status;
        renderStatus();
        return status;
    }

    async function runAction(control, action) {
        control.disabled = true;
        announce("Working…");
        try { await action(); }
        catch (error) { if (error?.name !== "AbortError") announce(error.message || "Operation failed.", true); }
        finally { control.disabled = false; }
    }

    function closeWorkspace() {
        password.value = "";
        controller.abort();
        if (typeof dialog.close === "function" && dialog.open) dialog.close();
        dialog.remove();
        workspace = null;
        previouslyFocused?.focus?.();
    }

    function selectTab(id) {
        activeTab = panels.has(id) ? id : "connection";
        for (const [tabId, panel] of panels) {
            panel.hidden = tabId !== activeTab;
            const tabButton = tabButtons.get(tabId);
            tabButton.setAttribute("aria-selected", String(tabId === activeTab));
            tabButton.tabIndex = tabId === activeTab ? 0 : -1;
        }
        if (activeTab === "tools") void loadTools();
        if (activeTab === "models") void loadModels();
    }

    tabs.addEventListener("keydown", event => {
        if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
        event.preventDefault();
        const ids = [...tabButtons.keys()];
        const index = ids.indexOf(activeTab);
        const next = event.key === "Home" ? 0 : event.key === "End" ? ids.length - 1
            : (index + (event.key === "ArrowRight" ? 1 : -1) + ids.length) % ids.length;
        selectTab(ids[next]);
        tabButtons.get(ids[next]).focus();
    });
    dialog.addEventListener("cancel", event => { event.preventDefault(); closeWorkspace(); });
    dialog.addEventListener("keydown", event => {
        if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); closeWorkspace(); }
    });
    dialog.addEventListener("click", event => { if (event.target === dialog) closeWorkspace(); });

    // Credentials only live in this short-lived password element, never in Comfy settings.
    const connection = panels.get("connection");
    const connectionGrid = node("div", "crun-connection-grid");
    const credentialPanel = node("div", "crun-surface");
    credentialPanel.append(node("h3", "", "Connect your CRUN account"), node("p", "crun-muted", "Save your key locally, then check the connection when you are ready."));
    const passwordLabel = node("label", "crun-label", "API key");
    passwordLabel.htmlFor = "crun-api-key-entry";
    const password = node("input", "crun-input");
    password.id = "crun-api-key-entry";
    password.type = "password";
    password.autocomplete = "off";
    password.spellcheck = false;
    password.placeholder = "Paste your CRUN API key";
    password.setAttribute("aria-describedby", "crun-key-privacy");
    const privacy = node("p", "crun-muted crun-small", "The key is sent only to this local ComfyUI backend. It is never included in workflow JSON or browser settings. The Check connection action contacts CRUN.");
    privacy.id = "crun-key-privacy";
    const credentialButtons = node("div", "crun-actions");
    const saveButton = button("Save key locally", () => runAction(saveButton, async () => {
        const value = password.value.trim();
        password.value = "";
        if (!value) throw new Error("Paste a CRUN API key before saving.");
        await localRequest("/credentials", { method: "POST", body: { api_key: value } });
        await readStatus();
        announce("Key saved locally. It has not been validated yet.");
    }), "crun-button crun-button-primary");
    const clearButton = button("Remove saved key", () => runAction(clearButton, async () => {
        password.value = "";
        await localRequest("/credentials/clear", { method: "POST", body: {} });
        balanceText.textContent = "Not checked";
        balanceTime.textContent = "";
        await readStatus();
        announce("Saved key removed. An environment key, if configured, still takes priority.");
    }));
    credentialButtons.append(saveButton, clearButton);
    const credentialStatus = node("p", "crun-key-status", "Reading local status…");
    credentialStatus.setAttribute("role", "status");
    credentialPanel.append(passwordLabel, password, privacy, credentialButtons, credentialStatus, link("Manage keys at CRUN ↗", "https://crun.ai/user-api-key"));
    const balancePanel = node("div", "crun-surface crun-balance");
    balancePanel.append(node("span", "crun-eyebrow", "ACCOUNT BALANCE"));
    const balanceText = node("strong", "crun-balance-value", "Not checked");
    const balanceTime = node("span", "crun-muted crun-small");
    const checkButton = button("Check connection & balance", () => runAction(checkButton, async () => {
        const result = await checkSavedConnection();
        await readStatus();
        balanceText.textContent = formatCredits(result.balance);
        balanceTime.textContent = `Checked ${new Date().toLocaleTimeString()}`;
        announce("Connection verified. Balance read from CRUN; no generation was submitted.");
    }), "crun-button crun-button-primary");
    balancePanel.append(balanceText, balanceTime, checkButton, node("p", "crun-muted crun-small", "CRUN credits are separate from KIE and Comfy credits. Balance is refreshed only when you request it."));
    connectionGrid.append(credentialPanel, balancePanel);
    connection.append(connectionGrid);

    function renderStatus() {
        if (!currentStatus) return;
        const source = currentStatus.source === "environment" || currentStatus.source === "env" ? "environment variable" : "local storage";
        credentialStatus.textContent = currentStatus.configured
            ? `Saved key via ${source}${currentStatus.key_hint ? ` · ${currentStatus.key_hint}` : ""}. ${connectionText(currentStatus)}.`
            : "No CRUN key configured. KIE settings remain unchanged.";
        if (currentStatus.last_balance !== null && currentStatus.last_balance !== undefined) {
            balanceText.textContent = formatCredits(currentStatus.last_balance);
            const checkedAt = currentStatus.balance_checked_at || currentStatus.checked_at;
            balanceTime.textContent = checkedAt ? `Last known balance · checked ${new Date(checkedAt * 1000).toLocaleString()}` : "Last known balance · not live";
        }
        dialog.dataset.version = String(currentStatus.version || "0.2.0");
    }

    const effects = panels.get("effects");
    const effectIntro = node("div", "crun-section-heading");
    effectIntro.append(node("h3", "", "AI Effects library"), node("p", "crun-muted", "Browse provider templates and prepare an effect plan here. Model-specific Comfy nodes offer prepare mode by default, with paid execution only when explicitly enabled."));
    const effectToolbar = node("div", "crun-toolbar");
    const providerLabel = node("label", "crun-label", "Provider");
    providerLabel.htmlFor = "crun-effect-provider";
    const providerSelect = node("select", "crun-input crun-provider");
    providerSelect.id = "crun-effect-provider";
    for (const provider of PROVIDERS) {
        const option = node("option", "", provider === "bytedance" ? "ByteDance" : provider === "vidu" ? "Vidu" : "Kling");
        option.value = provider;
        providerSelect.append(option);
    }
    providerSelect.addEventListener("change", () => { currentProvider = providerSelect.value; renderEffects(); });
    const refreshButton = button("Fetch catalog", async () => {
        const provider = currentProvider;
        if (pendingProviders.has(provider)) return;
        pendingProviders.add(provider);
        renderEffects();
        await runAction(refreshButton, async () => {
            const result = await localRequest("/effects/catalog", { method: "POST", body: { provider } });
            catalogs.set(provider, { cards: result.cards || [], fetchedAt: Date.now() });
            announce(`${result.cards?.length || 0} ${provider} templates received. No effect was generated.`);
        });
        pendingProviders.delete(provider);
        renderEffects();
    }, "crun-button crun-button-primary");
    const search = node("input", "crun-input crun-search");
    search.type = "search";
    search.placeholder = "Search effects by name, category or ID";
    search.setAttribute("aria-label", "Search the fetched effects catalog");
    search.addEventListener("input", renderEffects);
    effectToolbar.append(providerLabel, providerSelect, refreshButton, search);
    const effectSummary = node("p", "crun-muted crun-small");
    const effectGrid = node("div", "crun-card-grid");
    effects.append(effectIntro, effectToolbar, effectSummary, effectGrid);

    function renderEffects() {
        effectGrid.replaceChildren();
        const catalog = catalogs.get(currentProvider);
        if (!catalog) {
            effectSummary.textContent = pendingProviders.has(currentProvider) ? "Fetching catalog…" : "No catalog fetched. Fetching contacts CRUN with your saved key; it does not create a generation.";
            effectGrid.append(node("div", "crun-empty", "Choose a provider, then fetch its live catalog."));
            return;
        }
        const matching = filterEffects(catalog.cards, search.value);
        effectSummary.textContent = `${matching.length} of ${catalog.cards.length} templates · fetched ${new Date(catalog.fetchedAt).toLocaleTimeString()} · previews load only when requested`;
        if (!matching.length) effectGrid.append(node("div", "crun-empty", "No matching effects. Try another search."));
        for (const card of matching) {
            const item = node("article", "crun-effect-card");
            item.append(node("span", "crun-badge", card.category || currentProvider), node("h4", "", card.name || card.id), node("p", "crun-muted crun-small crun-template-id", card.id));
            const required = Number.isInteger(card.required_images) ? `${card.required_images} image slot${card.required_images === 1 ? "" : "s"}` : "Image slots: verify template";
            item.append(node("p", "crun-card-meta", required), node("p", "crun-card-meta", `Catalog cost: ${formatEffectCredits(card.credits)}`));
            const actions = node("div", "crun-actions");
            const previewUrl = safeRemoteUrl(card.preview_url);
            const coverUrl = safeRemoteUrl(card.cover_url);
            if (previewUrl || coverUrl) {
                const previewButton = button("Load preview", () => {
                    const media = node(previewUrl ? "video" : "img", "crun-preview");
                    media.referrerPolicy = "no-referrer";
                    if (previewUrl) {
                        media.controls = true;
                        media.preload = "metadata";
                        media.playsInline = true;
                        media.src = previewUrl;
                    } else {
                        media.alt = `${card.name || card.id} template preview`;
                        media.src = coverUrl;
                    }
                    item.insertBefore(media, actions);
                    previewButton.remove();
                });
                actions.append(previewButton);
            }
            actions.append(button("Prepare plan", () => showPlan(card)));
            item.append(actions);
            effectGrid.append(item);
        }
    }

    function showPlan(card) {
        let existing = effects.querySelector(".crun-plan");
        existing?.remove();
        const planPanel = node("section", "crun-surface crun-plan");
        planPanel.append(node("h3", "", `Effect plan · ${card.name || card.id}`), node("p", "crun-muted", "This is a project planning format, not an executable API payload. No images are uploaded and no credits are spent."));
        const planText = node("textarea", "crun-input crun-plan-json");
        planText.readOnly = true;
        planText.value = JSON.stringify(effectPlan(card), null, 2);
        planText.setAttribute("aria-label", "Prepared effect plan JSON");
        const copyButton = button("Copy plan JSON", async () => {
            try {
                await navigator.clipboard.writeText(planText.value);
                announce("Effect plan copied. This does not submit a task.");
            } catch {
                planText.focus();
                planText.select();
                announce("Select and copy the plan text manually; clipboard access is unavailable.");
            }
        });
        planPanel.append(planText, copyButton);
        effects.append(planPanel);
        planText.focus();
    }

    const modelsPanel = panels.get("models");
    modelsPanel.append(node("h3", "", "Model library"), node("p", "crun-muted", "Inspect documented operations and their exact inputs. Explicit refresh fetches public definitions and, when configured, checks the account's read-only LLM inventory. A catalog listing is not a successful generation test."));
    const modelsToolbar = node("div", "crun-toolbar");
    const modelSearch = node("input", "crun-input crun-search");
    modelSearch.type = "search";
    modelSearch.placeholder = "Search models, providers or input names";
    modelSearch.setAttribute("aria-label", "Search model catalog");
    const modelProvider = node("select", "crun-input crun-provider");
    modelProvider.setAttribute("aria-label", "Filter models by provider");
    const modelKind = node("select", "crun-input crun-provider");
    modelKind.setAttribute("aria-label", "Filter models by task kind");
    let modelSnapshot = null;
    let modelLoading = false;
    const modelSummary = node("p", "crun-muted crun-small");
    const modelGrid = node("div", "crun-card-grid");
    const modelDetails = node("section", "crun-surface crun-model-details");
    modelDetails.hidden = true;
    const refreshModels = button("Refresh public model definitions", () => runAction(refreshModels, async () => {
        const result = await localRequest("/models/refresh", { method: "POST", body: {} });
        modelSnapshot = result.catalog || result;
        updateModelFilters();
        renderModels();
        announce("Catalog refreshed. Any account inventory included is a read-only snapshot; no generation was submitted.");
    }), "crun-button crun-button-primary");
    modelsToolbar.append(modelSearch, modelProvider, modelKind, refreshModels);
    modelsPanel.append(modelsToolbar, modelSummary, modelGrid, modelDetails);
    modelSearch.addEventListener("input", renderModels);
    modelProvider.addEventListener("change", renderModels);
    modelKind.addEventListener("change", renderModels);

    async function loadModels() {
        if (modelSnapshot || modelLoading) return;
        modelLoading = true;
        modelSummary.textContent = "Reading local catalog snapshot…";
        try {
            const result = await localRequest("/models");
            modelSnapshot = result.catalog || result;
            updateModelFilters();
            renderModels();
        } catch (error) {
            modelSummary.textContent = error.message || "Model catalog unavailable.";
        } finally { modelLoading = false; }
    }

    function updateModelFilters() {
        const entries = Array.isArray(modelSnapshot?.entries) ? modelSnapshot.entries : [];
        for (const [select, field, allLabel] of [[modelProvider, "provider", "All providers"], [modelKind, "kind", "All task kinds"]]) {
            const previous = select.value;
            select.replaceChildren();
            const any = node("option", "", allLabel);
            any.value = "";
            select.append(any);
            for (const value of [...new Set(entries.map(entry => String(entry[field] || "unknown")))].sort()) {
                const option = node("option", "", value);
                option.value = value;
                select.append(option);
            }
            select.value = [...select.children].some(option => option.value === previous) ? previous : "";
        }
    }

    function renderModels() {
        const entries = Array.isArray(modelSnapshot?.entries) ? modelSnapshot.entries : [];
        const query = modelSearch.value.trim().toLowerCase();
        const matching = entries.filter(entry => (!modelProvider.value || entry.provider === modelProvider.value)
            && (!modelKind.value || entry.kind === modelKind.value)
            && [entry.title, entry.model, entry.provider, entry.kind, JSON.stringify(entry.inputs?.properties || {})]
                .some(value => String(value || "").toLowerCase().includes(query)));
        const summary = modelSnapshot?.summary || {};
        const refreshed = modelSnapshot?.refreshed_at;
        const refreshedText = refreshed ? ` · snapshot ${new Date(typeof refreshed === "number" ? refreshed * 1000 : refreshed).toLocaleString()}` : " · not refreshed yet";
        modelSummary.textContent = `${summary.unique_model_count ?? new Set(entries.map(entry => entry.model)).size} model IDs · ${entries.length} documented operations · ${matching.length} match${refreshedText}${matching.length > 100 ? " · showing first 100; filter to narrow" : ""}`;
        modelGrid.replaceChildren();
        if (!matching.length) modelGrid.append(node("p", "crun-empty", entries.length ? "No matching model operations." : "No local model catalog yet. Refresh public model definitions to discover operations."));
        for (const entry of matching.slice(0, 100)) {
            const card = node("article", "crun-effect-card");
            card.append(node("span", "crun-badge", `${entry.provider || "CRUN"} · ${entry.kind || "model"}`), node("h4", "", entry.title || entry.model || entry.operation_id || entry.id), node("p", "crun-muted crun-small crun-template-id", entry.model || entry.operation_id || entry.id));
            card.append(node("p", "crun-muted crun-small", modelAvailabilityText(entry, modelSnapshot?.account_catalog_checked_at)));
            card.append(button("Inspect inputs", () => showModelDetails(entry)));
            modelGrid.append(card);
        }
    }

    function showModelDetails(entry) {
        modelDetails.hidden = false;
        modelDetails.replaceChildren(node("h3", "", entry.title || entry.model || entry.operation_id || entry.id), node("p", "crun-template-id", entry.model || entry.operation_id || entry.id), node("p", "crun-muted crun-small", `${entry.method || ""} ${entry.endpoint || ""} · ${entry.auth || "see definition"}`));
        const schema = entry.inputs || entry.input_schema || {};
        const schemaBox = node("textarea", "crun-input crun-plan-json");
        schemaBox.readOnly = true;
        schemaBox.setAttribute("aria-label", "Documented model input schema");
        schemaBox.value = JSON.stringify(schema, null, 2);
        modelDetails.append(node("p", "crun-muted crun-small", modelAvailabilityText(entry, modelSnapshot?.account_catalog_checked_at)), node("p", "crun-muted", "Required fields, enums, nested objects and references follow the published schema below. This panel does not submit requests."), schemaBox);
        if (safeRemoteUrl(entry.documentation_url)) modelDetails.append(link("Official operation documentation ↗", entry.documentation_url));
        schemaBox.focus();
    }

    const toolsPanel = panels.get("tools");
    toolsPanel.append(node("h3", "", "AI Tools workbench"), node("p", "crun-muted", "Explore every documented utility from the current model catalog. Model-specific nodes are available under CRUN Next → AI Tools. They prepare by default; paid execution requires explicit enablement. These workspace cards do not run tasks."));
    const toolsGrid = node("div", "crun-card-grid");
    const toolDetails = node("section", "crun-surface crun-model-details");
    toolDetails.hidden = true;
    toolsPanel.append(toolsGrid, toolDetails);
    async function loadTools() {
        if (tools !== null || toolsPending) return;
        toolsPending = true;
        toolsGrid.replaceChildren(node("p", "crun-muted", "Loading local tools index…"));
        try {
            const result = await localRequest("/tools");
            tools = result.tools || [];
            toolsGrid.replaceChildren();
            for (const tool of tools) {
                const card = node("article", "crun-effect-card");
                const readiness = tool.status === "node_available" ? "COMFY NODE AVAILABLE · DEFAULT PREPARE" : "DOCUMENTED · VERIFY NODE AVAILABILITY";
                card.append(node("span", "crun-badge", readiness), node("h4", "", tool.name || tool.id), node("p", "crun-muted crun-small", tool.category || "AI Tool"), node("p", "", tool.description || ""));
                if (tool.node_menu) card.append(node("p", "crun-muted crun-small crun-template-id", `Nodes menu: ${tool.node_menu}`));
                if (tool.usage_note) card.append(node("p", "crun-muted crun-small", tool.usage_note));
                card.append(button("Inspect tool inputs", () => {
                    toolDetails.hidden = false;
                    toolDetails.replaceChildren(node("h3", "", tool.name || tool.model || tool.id));
                    const schema = node("textarea", "crun-input crun-plan-json");
                    schema.readOnly = true;
                    schema.setAttribute("aria-label", "Documented tool input schema");
                    schema.value = JSON.stringify(tool.input_schema || {}, null, 2);
                    toolDetails.append(node("p", "crun-muted", "These controls are exposed in the model-specific Comfy node. Inspecting this definition does not submit a task."), schema);
                    schema.focus();
                }));
                const docs = safeRemoteUrl(tool.documentation_url);
                if (docs) card.append(link("Read API definition ↗", docs));
                toolsGrid.append(card);
            }
            if (!tools.length) toolsGrid.append(node("p", "crun-empty", "No tool definitions in this build."));
        } catch (error) {
            toolsGrid.replaceChildren(node("p", "crun-error", error.message || "Tools index unavailable."));
            toolsGrid.append(button("Retry local index", () => { toolsPending = false; void loadTools(); }));
        } finally { toolsPending = false; }
    }

    workspace = { dialog, selectTab };
    renderEffects();
    selectTab(initialTab);
    if (typeof dialog.showModal === "function") dialog.showModal();
    else dialog.setAttribute("open", "");
    close.focus();
    void readStatus().catch(error => announce(error.message || "Could not read local configuration.", true));
}

function settingsAction(control, message, action) {
    return async () => {
        control.disabled = true;
        message.textContent = "Working…";
        try { await action(); }
        catch (error) { message.textContent = error.message || "CRUN Next action failed."; }
        finally { control.disabled = false; }
    };
}

// A custom renderer never calls the settings setter with a credential. Its value
// remains empty; the secret is posted directly to the protected local backend.
export function renderConnectionSetting(kind) {
    installStyles();
    const row = node("div", "crun-settings-row");
    const info = node("p", "crun-settings-text", "Reading saved backend state…");
    const message = node("p", "crun-small crun-settings-message");
    message.setAttribute("role", "status");
    const controls = node("div", "crun-settings-controls");
    row.append(info, controls, message);
    if (kind === "key") {
        const input = node("input", "crun-input");
        input.type = "password";
        input.autocomplete = "off";
        input.spellcheck = false;
        input.placeholder = "Paste / replace CRUN API key";
        input.setAttribute("aria-label", "Paste or replace CRUN API key");
        if (typeof MutationObserver !== "undefined") {
            let wasConnected = false;
            const observer = new MutationObserver(() => {
                if (row.isConnected) wasConnected = true;
                else if (wasConnected) {
                    input.value = "";
                    observer.disconnect();
                }
            });
            observer.observe(document.body, { childList: true, subtree: true });
        }
        const save = button("Save key", () => {} , "crun-button crun-button-primary");
        save.addEventListener("click", settingsAction(save, message, async () => {
            const value = input.value.trim();
            input.value = "";
            if (!value) throw new Error("Paste a CRUN key before saving.");
            await localApiRequest("/credentials", { method: "POST", body: { api_key: value } });
            await readPublicStatus();
            message.textContent = "Key saved on the backend. Only its masked fingerprint remains visible.";
        }));
        controls.append(input, save);
    } else if (kind === "connection") {
        const check = button("Test saved key & refresh balance", () => {}, "crun-button crun-button-primary");
        check.addEventListener("click", settingsAction(check, message, async () => {
            await checkSavedConnection();
            message.textContent = "Connection checked with CRUN. No generation submitted.";
        }));
        controls.append(check);
    } else if (kind === "balance") {
        const refresh = button("Refresh balance", () => {});
        refresh.addEventListener("click", settingsAction(refresh, message, async () => {
            await checkSavedConnection();
            message.textContent = "Last known balance updated from CRUN.";
        }));
        controls.append(refresh);
    } else if (kind === "saved") {
        const remove = button("Remove saved key", () => {});
        remove.addEventListener("click", settingsAction(remove, message, async () => {
            await localApiRequest("/credentials/clear", { method: "POST", body: {} });
            await readPublicStatus();
            message.textContent = "Saved key removed. Environment credentials, if set, are not modified.";
        }));
        controls.append(remove);
    }
    const refreshView = status => {
        if (!status) { info.textContent = "Checking saved backend state…"; return; }
        if (kind === "key") info.textContent = "Paste once; stored outside workflows and browser settings.";
        else if (kind === "saved") info.textContent = status.configured
            ? `Saved key: ${status.key_hint || "••••"} · ${status.source === "environment" ? "environment override" : status.storage || "backend"}`
            : "No API key saved";
        else if (kind === "connection") info.textContent = connectionText(status);
        else if (kind === "balance") {
            const checkedAt = status.balance_checked_at || status.checked_at;
            info.textContent = status.last_balance !== null && status.last_balance !== undefined
                ? `Last known balance: ${formatCredits(status.last_balance)}${checkedAt ? ` · checked ${new Date(checkedAt * 1000).toLocaleString()}` : ""} · not a live balance`
                : "Balance not checked. CRUN credits are separate from KIE and Comfy.";
        }
    };
    settingsViews.set(kind, refreshView);
    refreshView(latestStatus);
    // This reads only local state, never the provider balance automatically.
    void readPublicStatus().catch(() => { info.textContent = "Backend unavailable. Restart ComfyUI after installation."; });
    return row;
}

app.registerExtension({
    name: "CRUN.Next.Workspace",
    commands: [
        { id: "CRUNNext.OpenWorkspace", label: "Open CRUN Next", function: () => openCrunWorkspace() },
        { id: "CRUNNext.OpenModels", label: "Model library", function: () => openCrunWorkspace("models") },
        { id: "CRUNNext.OpenEffects", label: "AI Effects", function: () => openCrunWorkspace("effects") },
        { id: "CRUNNext.OpenTools", label: "AI Tools", function: () => openCrunWorkspace("tools") },
    ],
    menuCommands: [{ path: ["Extensions", "CRUN Next"], commands: ["CRUNNext.OpenWorkspace", "CRUNNext.OpenModels", "CRUNNext.OpenEffects", "CRUNNext.OpenTools"] }],
    settings: [
        ...[
            ["APIKeyEntry", "Paste / replace CRUN API key", "key"],
            ["SavedKey", "Saved API key", "saved"],
            ["ConnectionState", "CRUN connection", "connection"],
            ["CreditBalance", "Credit balance", "balance"],
        ].map(([id, name, kind]) => ({
            id: `CRUNNext.Connection.${id}`, name,
            category: ["CRUN Next", "Connection", name],
            type: () => renderConnectionSetting(kind),
            defaultValue: "",
            tooltip: "Live backend state. API credentials are never written to Comfy's setting values.",
        })),
        {
        id: OPEN_SETTING,
        name: "Open connection & creative workspace",
        category: ["CRUN Next", "Connection", "Open workspace"],
        type: "boolean",
        defaultValue: false,
        tooltip: "Open the CRUN Next workspace to save your API key securely on the local backend. No key is stored in this setting.",
        onChange(setting, newValue) {
            const value = typeof newValue === "undefined" ? setting : newValue;
            if (value !== true) return;
            openCrunWorkspace();
            const settings = app.extensionManager?.setting;
            if (settings?.set) void settings.set(OPEN_SETTING, false).catch(() => {});
            else app.ui?.settings?.setSettingValue?.(OPEN_SETTING, false);
        },
        },
    ],
    setup() {
        installStyles();
        // A small discoverable launcher is also a fallback for older Comfy frontends.
        if (!document.getElementById("crun-next-launcher")) {
            const launcher = button("CRUN Next", () => openCrunWorkspace(), "crun-launcher");
            launcher.id = "crun-next-launcher";
            launcher.title = "Open CRUN Next connection, AI Effects and AI Tools";
            document.body.append(launcher);
        }
    },
});

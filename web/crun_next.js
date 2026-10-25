import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

const ROOT = "/crun-next";
const OPEN_SETTING = "CRUNNext.Workspace.Open";
const PROVIDERS = ["kling", "bytedance", "vidu"];
let workspace = null;

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
        execution: "disabled_in_skeleton",
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
    let nonce = "";
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
    const notice = node("div", "crun-notice", "Foundation release · No paid generation or upload can run from this workspace.");
    const tabs = node("div", "crun-tabs");
    tabs.setAttribute("role", "tablist");
    tabs.setAttribute("aria-label", "CRUN workspace sections");
    const tabButtons = new Map();
    const panels = new Map();
    const content = node("div", "crun-content");
    const feedback = node("p", "crun-feedback");
    feedback.setAttribute("role", "status");
    feedback.setAttribute("aria-live", "polite");
    for (const [id, label] of [["connection", "Connection"], ["effects", "AI Effects"], ["tools", "AI Tools"]]) {
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

    async function localRequest(path, { method = "GET", body, useNonce = true } = {}) {
        if (useNonce && !nonce) await readStatus();
        const headers = { Accept: "application/json" };
        if (useNonce) headers["X-CRUN-Nonce"] = nonce;
        if (body !== undefined) headers["Content-Type"] = "application/json";
        let response;
        try {
            response = await api.fetchApi(`${ROOT}${path}`, {
                method, headers, body: body === undefined ? undefined : JSON.stringify(body),
                cache: "no-store", signal: controller.signal,
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

    async function readStatus() {
        const status = await localRequest("/status", { useNonce: false });
        nonce = status.nonce || "";
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
        const result = await localRequest("/connection", { method: "POST", body: {} });
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
            ? `Key configured via ${source}${currentStatus.key_hint ? ` · ${currentStatus.key_hint}` : ""}. Saved is not the same as verified.`
            : "No CRUN key configured. KIE settings remain unchanged.";
        dialog.dataset.version = String(currentStatus.version || "0.1.0");
    }

    const effects = panels.get("effects");
    const effectIntro = node("div", "crun-section-heading");
    effectIntro.append(node("h3", "", "AI Effects library"), node("p", "crun-muted", "Browse provider templates and prepare an effect plan. Execution is intentionally disabled in this foundation release."));
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

    const toolsPanel = panels.get("tools");
    toolsPanel.append(node("h3", "", "AI Tools workbench"), node("p", "crun-muted", "A curated roadmap of CRUN utilities. These cards are documentation only—not runnable nodes yet."));
    const toolsGrid = node("div", "crun-card-grid");
    toolsPanel.append(toolsGrid);
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
                card.append(node("span", "crun-badge", "PLANNED · NOT RUNNABLE"), node("h4", "", tool.name || tool.id), node("p", "crun-muted crun-small", tool.category || "AI Tool"), node("p", "", tool.description || ""));
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

app.registerExtension({
    name: "CRUN.Next.Workspace",
    commands: [{ id: "CRUNNext.OpenWorkspace", label: "Open CRUN Next", function: () => openCrunWorkspace() }],
    menuCommands: [{ path: ["Extensions", "CRUN Next"], commands: ["CRUNNext.OpenWorkspace"] }],
    settings: [{
        id: OPEN_SETTING,
        name: "Open connection & creative workspace",
        category: ["CRUN Next", "Connection", "Open workspace"],
        type: "boolean",
        defaultValue: false,
        tooltip: "Open the CRUN Next workspace to save your API key securely on the local backend. No key is stored in this setting.",
        onChange(value) {
            if (value !== true) return;
            openCrunWorkspace();
            const settings = app.extensionManager?.setting;
            if (settings?.set) void settings.set(OPEN_SETTING, false);
            else app.ui?.settings?.setSettingValue?.(OPEN_SETTING, false);
        },
    }],
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

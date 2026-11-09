-- Wrath 3.3.5 UI runtime. Imported D3 callbacks are never executed as code.
D3UI = { handlers = {}, frames = {} }
local data = D3UIData
local function say(message) DEFAULT_CHAT_FRAME:AddMessage("D3 UI: " .. message) end
function D3UI.RegisterHandler(name, callback)
    assert(type(name) == "string" and type(callback) == "function")
    D3UI.handlers[name] = callback
end
local function apply(texture, name)
    local a = data.assets[name]
    if not a then return false end
    texture:SetTexture(a.file)
    texture:SetTexCoord(unpack(a.uv))
    return true
end
local function shell(name)
    local f = CreateFrame("Frame", name, UIParent)
    f:SetWidth(1600); f:SetHeight(1200); f:SetPoint("CENTER")
    f:SetScale(math.min(UIParent:GetWidth() / 1600, UIParent:GetHeight() / 1200) * 0.94)
    f:SetFrameStrata("DIALOG"); f:EnableMouse(true)
    f:SetBackdrop({bgFile = "Interface\\Tooltips\\UI-Tooltip-Background"})
    f:SetBackdropColor(0.025, 0.025, 0.03, 0.97)
    local close = CreateFrame("Button", nil, f, "UIPanelCloseButton")
    close:SetPoint("TOPRIGHT"); close:SetFrameLevel(f:GetFrameLevel() + 100)
    close:SetScript("OnClick", function() f:Hide() end)
    table.insert(UISpecialFrames, name)
    return f
end
local function dispatch(c, f)
    local callback = c.callbacks["41"]
    if callback and D3UI.handlers[callback] then
        D3UI.handlers[callback](f, c)
    else
        say("No gameplay handler: " .. (callback or c.path))
    end
end
local function selectPanel(root, name, panel)
    local choices = data.views[name] or {}
    if #choices == 0 then return end
    local chosen = choices[1]
    for _, path in ipairs(choices) do
        if path == panel or string.match(path, "([^.]+)$") == panel then chosen = path end
    end
    for _, path in ipairs(choices) do
        if path == chosen then root.nodes[path]:Show() else root.nodes[path]:Hide() end
    end
end
function D3UI.Show(name, panel)
    if not data.windows[name] then say("Windows: Paragon, SkillPane, SkillBar, Traits"); return end
    if panel == "list" then
        for _, path in ipairs(data.views[name] or {}) do say(string.match(path, "([^.]+)$")) end
        return
    end
    for _, f in pairs(D3UI.frames) do f:Hide() end
    if D3UI.frames[name] then
        D3UI.frames[name]:Show(); selectPanel(D3UI.frames[name], name, panel); return
    end
    local root = shell("D3UIWindow" .. name)
    D3UI.frames[name] = root
    local nodes = {}
    root.nodes = nodes
    for _, c in ipairs(data.windows[name]) do
        local parent = nodes[c.parent] or root
        local clickable = c.type == 3 or c.type == 22
        local f = CreateFrame(clickable and "Button" or "Frame", nil, parent)
        f:SetWidth(math.max(1, c.width)); f:SetHeight(math.max(1, c.height))
        f:SetPoint("TOPLEFT", parent, "TOPLEFT", c.x, -c.y)
        nodes[c.path] = f
        if c.textures.normal then
            local t = f:CreateTexture(nil, "BACKGROUND"); t:SetAllPoints(f)
            apply(t, c.textures.normal)
        end
        if clickable then
            for state, setter in pairs({highlight="SetHighlightTexture", pushed="SetPushedTexture", disabled="SetDisabledTexture"}) do
                if c.textures[state] then
                    local t = f:CreateTexture(nil, "ARTWORK"); t:SetAllPoints(f)
                    if apply(t, c.textures[state]) then f[setter](f, t) end
                end
            end
            f:SetScript("OnClick", function() dispatch(c, f) end)
            f:SetScript("OnEnter", function()
                GameTooltip:SetOwner(f, "ANCHOR_RIGHT"); GameTooltip:SetText(c.name)
                GameTooltip:AddLine(c.callbacks["41"] or c.path, 0.7, 0.7, 0.7, true)
                GameTooltip:Show()
            end)
            f:SetScript("OnLeave", function() GameTooltip:Hide() end)
        end
        if (c.type == 4 or clickable) and c.text ~= "" then
            local text = f:CreateFontString(nil, "OVERLAY", "GameFontNormal")
            text:SetAllPoints(f); text:SetFont("Fonts\\FRIZQT__.TTF", math.max(8, c.font_size))
            text:SetText(c.text); text:SetJustifyH(clickable and "CENTER" or "LEFT")
        end
        if c.hidden then f:Hide() end
    end
    selectPanel(root, name, panel)
end
local browser, items, page, query
local function refreshIcons()
    local perPage = 84
    for i, button in ipairs(items) do
        local name = query[(page - 1) * perPage + i]
        button.sprite = name
        if name then apply(button.image, name); button:Show() else button:Hide() end
    end
    browser.title:SetText("D3 icons: " .. #query .. " results | Page " .. page .. "/" .. math.max(1, math.ceil(#query / perPage)))
end
function D3UI.ShowIcons(search)
    if not browser then
        browser = shell("D3UIIconBrowser"); items = {}
        browser.title = browser:CreateFontString(nil, "OVERLAY", "GameFontNormalLarge")
        browser.title:SetPoint("TOP", 0, -35)
        for i = 1, 84 do
            local b = CreateFrame("Button", nil, browser)
            b:SetWidth(90); b:SetHeight(90)
            b:SetPoint("TOPLEFT", 45 + ((i - 1) % 12) * 125, -110 - math.floor((i - 1) / 12) * 140)
            b.image = b:CreateTexture(nil, "ARTWORK"); b.image:SetAllPoints(b)
            b:SetScript("OnEnter", function()
                GameTooltip:SetOwner(b, "ANCHOR_RIGHT"); GameTooltip:SetText(b.sprite or "")
                GameTooltip:Show()
            end)
            b:SetScript("OnLeave", function() GameTooltip:Hide() end)
            b:SetScript("OnClick", function() say(b.sprite or "") end)
            items[i] = b
        end
        for i, label in ipairs({"Previous", "Next"}) do
            local b = CreateFrame("Button", nil, browser, "UIPanelButtonTemplate")
            b:SetWidth(150); b:SetHeight(35); b:SetText(label)
            b:SetPoint("BOTTOM", (i == 1 and -100 or 100), 30)
            local delta = i == 1 and -1 or 1
            b:SetScript("OnClick", function()
                page = math.max(1, math.min(math.max(1, math.ceil(#query / 84)), page + delta)); refreshIcons()
            end)
        end
    end
    query = {}; page = 1; search = string.lower(search or "")
    for _, name in ipairs(data.icons) do
        if string.find(string.lower(name), search, 1, true) then table.insert(query, name) end
    end
    refreshIcons(); browser:Show()
end
SLASH_D3UI1 = "/d3ui"
SlashCmdList.D3UI = function(message)
    local name, panel = string.match(message, "^%s*(%S*)%s*(%S*)")
    D3UI.Show(name ~= "" and name or "Paragon", panel)
end
SLASH_D3ICONS1 = "/d3icons"
SlashCmdList.D3ICONS = D3UI.ShowIcons

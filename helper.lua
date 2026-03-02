local M = {}

function M.format_price_no_currency(currency, value)
    if currency == "EUR" then
        return string.format("%.2f", value):gsub('[.]', ',')
    else
        return string.format("%.2f", value)
    end
end

function M.format_price(currency, value)
    if currency == "EUR" then
        return M.format_price_no_currency(currency, value) .. "€"
    else
        return M.format_price_no_currency(currency, value) .. " " .. currency
    end
end

function M.img_centered(img, cx, cy, max_w, max_h)
    local ox1, oy1, ox2, oy2 = util.scale_into(
        max_w, max_h, img:size()
    )
    return img:draw(
        cx - max_w/2 + ox1,
        cy - max_h/2 + oy1,
        cx - max_w/2 + ox2,
        cy - max_h/2 + oy2
    )
end

function M.centered_text(font, cx, y, text, size, r,g,b,a)
    local w = font:width(text, size)
    return font:write(math.floor(cx-w/2), math.floor(y), text, size, r,g,b,a)
end

function M.wrap(str, font, size, max_w)
    local lines = {}
    local space_w = font:width(" ", size)

    local remaining = max_w
    local line = {}
    for non_space in str:gmatch("%S+") do
        local w = font:width(non_space, size)
        if remaining - w < 0 then
            lines[#lines+1] = table.concat(line, "")
            line = {}
            remaining = max_w
        end
        line[#line+1] = non_space
        line[#line+1] = " "
        remaining = remaining - w - space_w
    end
    if #line > 0 then
        lines[#lines+1] = table.concat(line, "")
    end
    return lines
end

return M

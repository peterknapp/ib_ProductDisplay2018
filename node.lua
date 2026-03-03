gl.setup(NATIVE_WIDTH, NATIVE_HEIGHT)
-- bump

util.no_globals()
node.make_nested()

local min, max = math.min, math.max
local matrix = require "matrix2d"
local helper = require "helper"
local SyncedData = require("datasync/client").SyncedData

local ny_assets = {
    pi = { -- Produktinformationen
        background = resource.load_image "ny-product-background.jpg",
        price_overlay = resource.load_image "ny-price-overlay.png",
        black = resource.create_colored_texture(0, 0, 0, 1),
        matching_box = resource.load_image{
            file = "ny-product-matching-box.png",
            nearest = true,
        },
        gradient = resource.load_image{
            file = "ny-product-gradient.jpg",
            nearest = true,
        },
    },

    sty = { -- Lifestyle Page
        background = resource.create_colored_texture(1,1,1, .8),
        logo = resource.load_image "ny-lifestyle-logo.png",
    },

    font = {
        regl = resource.load_font "font-regl.otf";
        thin = resource.load_font "font-thin.otf";
        bold = resource.load_font "font-bold.otf";
    },

    -- XXX
    fallback = resource.load_image{
        file = "package.png";
        nearest = true;
    }
}

local function Time()
    local offset = 0
    local function set_offset(new_offset)
        print("setting screen time offset to", new_offset)
        offset = new_offset
    end
    local function get()
        return os.time() + offset
    end
    return {
        set_offset = set_offset,
        get = get,
    }
end
local time = Time()

local function SlotLoader(item_type)
    -- Helper function to load cross devices synchronized data. SyncedData wraps
    -- around the files created by the service in datasync. Synced data is organized
    -- by key. New updates a a key are atomic and versioned. This code uses a single key
    -- for each pages that requires shared data: e.g. the product page or the style page.
    --
    -- datasync/<key>.json holds the versioned information about each key. Each version
    -- of a key has a commit_time and can hold any number of files for that version.
    -- By convension we also use <key>.json as the main data file for each version.
    -- It's created by the corresponding python code in ny_*_page.py.
    --
    -- Inside each <key>.json file in a version is all the data for the different
    -- instances of (for example) a product page. The "slot_id" is the position inside
    -- the current playlist.
    --
    -- This is probably easiest to see if you poke into a running info-beamer device
    -- and have a look at datasync/product.json and the files it references.
    local data_source = SyncedData(item_type)

    return function(pinned_time, slot_id)
        local version = data_source.json_at(pinned_time, item_type .. ".json")
        if not version then
            return
        end
        local slots = version.slots
        local slot = slots[tostring(slot_id)]
        return slot, {
            load_image = function(name)
                return resource.load_image(
                    data_source.file_at(pinned_time, name)
                )
            end
        }
    end
end

local function choice(true_false, true_val, false_val)
    if true_false then
        return true_val
    else
        return false_val
    end
end

local function TestMode()
    local test_mode_until = 0
    util.data_mapper{
        test = function()
            test_mode_until = sys.now() + 30
        end
    }
    return function()
        return sys.now() < test_mode_until
    end
end
local testing = TestMode()


local function I18N()
    local i18n = {}

    util.json_watch("i18n.json", function(new_mapping)
        print("updated i18n")
        i18n = new_mapping
    end)

    local function translate(key, fallback)
        local translated = i18n[key]
        return translated or fallback
    end

    return translate
end
local T = I18N()


local function VirtualScreen()
    local width, height, screen, virtual2pixel

    local function inverted_rotation(rot)
        return math.fmod((360 - rot) / 90, 4) * 90
    end

    local function update(new_screen, new_width, new_height)
        width = new_width
        height = new_height
        screen = new_screen
        virtual2pixel = matrix.scale(NATIVE_WIDTH / screen.w,
                                     NATIVE_HEIGHT / screen.h)
                      * matrix.rotate_deg(inverted_rotation(screen.rotation))
                      * matrix.trans(-screen.x, -screen.y)
    end

    local function project(x1, y1, x2, y2)
        x1, y1 = virtual2pixel(x1, y1)
        x2, y2 = virtual2pixel(x2, y2)
        return min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)
    end

    local function video(vid, x1, y1, x2, y2, layer)
        layer = layer or 1
        x1, y1, x2, y2 = project(x1, y1, x2, y2)
        return vid:place(
            x1, y1, x2, y2, inverted_rotation(screen.rotation)
        ):layer(layer)
    end

    local function setup()
        gl.scale(NATIVE_WIDTH / screen.w, NATIVE_HEIGHT / screen.h)
        gl.rotate(inverted_rotation(screen.rotation), 0, 0, 1)
        gl.translate(-screen.x, -screen.y)
    end

    local function covers(x1, y1, x2, y2)
        -- check is this screen configuration shows
        -- content within the given rectangle.
        x1, y1, x2, y2 = project(x1, y1, x2, y2)
        return x1 < NATIVE_WIDTH and x2 > 0 and
               y1 < NATIVE_HEIGHT and y2 > 0
    end

    local function info()
        return screen
    end

    return {
        update = update;
        covers = covers;
        setup = setup;
        video = video;
        info = info;
    }
end
local screen = VirtualScreen()


local function ContentArea()
    local landscape = true

    -- We emulate a 4K area. So rendering content
    -- with e.g. font:write can use coordinates as
    -- if there's a 4K display connected. For single
    -- screens the content is downscaled. For 2x2
    -- video walls, fonts are perfectly clear as they
    -- are not getting upscaled.
    local emulated_width = 1920*2
    local emulated_height = 1080*2

    local function size()
        if landscape then
            _G.WIDTH = emulated_width
            _G.HEIGHT = emulated_height
            return emulated_width, emulated_height
        else
            _G.WIDTH = emulated_height
            _G.HEIGHT = emulated_width
            return emulated_height, emulated_width
        end
    end

    local function update(new_landscape)
        landscape = new_landscape
    end

    local function is_landscape()
        return landscape
    end

    return {
        size = size;
        update = update;
        is_landscape = is_landscape,
    }
end
local content_area = ContentArea()


local function PlayState(start_t, duration)
    local end_t
    local on_screen = false
    local function get(now)
        local from_start = now - start_t
        local to_end = 10000000
        if end_t then
            to_end = end_t - now
        end
        if now >= start_t then
            on_screen = true
        end
        return now, on_screen, from_start, to_end
    end
    local function set_end(t)
        end_t = t
    end
    local function get_earliest_end()
        return start_t + duration
    end
    local function get_start()
        return start_t
    end
    return {
        set_end = set_end;
        get_earliest_end = get_earliest_end,
        get_start = get_start,
        get = get;
    }
end


local function select_lod_assets(opt)
    -- Expected options: max_lod, max_assets, assets
    --
    -- Select one or more assets from a list of assets organized
    -- in a level-of-details (lod) way like this:
    -- 
    -- [
    --   <asset-full>,
    --   <asset-1/4th-top-left>,
    --   <asset-1/4th-top-right>,
    --   <asset-1/4th-bottom-left>,
    --   <asset-1/4th-bottom-right>,
    --   <asset-1/9th-top-left>,
    --   <asset-1/9th-top-middle>,
    --   ...
    -- ]
    --
    -- This function will select the best fitting asset(s) that
    -- are visible on the current screen configuration. It will
    -- try to select the highest level of details, unless the
    -- resulting number of assets is higher than max_assets.
    -- In which case if will fall back to a lower level of
    -- detail until at most max_assets assets are selected. The
    -- fallback is always to select the <asset-full>.
    --
    -- For images, it makes sense to allow max_assets=4, as loading
    -- images only happens once and it's ok to have them all
    -- loaded at once.
    --
    -- For videos, max_assets should be 1, as playing multiple
    -- videos at once might result in a bad/broken output.
    local lods = {}
    local asset_idx = 0
    for lod = 1, opt.max_lod do
        lods[lod] = {}
        local lod_assets = lods[lod]
        local w = WIDTH / lod
        local h = HEIGHT / lod
        for y = 0, lod-1 do
            for x = 0, lod-1 do
                asset_idx = asset_idx + 1
                if screen.covers(x*w+1, y*h+1, (x+1)*w-1, (y+1)*h-1) then
                    lod_assets[#lod_assets+1] = {
                        x1 = x*w,
                        y1 = y*h,
                        x2 = (x+1)*w,
                        y2 = (y+1)*h,
                        asset = opt.assets[asset_idx],
                    }
                end
            end
        end
    end

    local lod_assets
    for lod = opt.max_lod, 1, -1 do
        if #lods[lod] <= opt.max_assets then
            local all_assets_available = true
            lod_assets = lods[lod]
            for idx = 1, #lod_assets do
                if not lod_assets[idx].asset then
                    all_assets_available = false
                end
            end
            if all_assets_available then
                break
            end
        end
    end
    return lod_assets
end


local function Image(play_state, config)
    local img

    local assets = select_lod_assets{
        max_lod = 3, -- support up to 6K (=3x3 FullHD)
        max_assets = 4, -- we can load 4 images at once
        assets = config.assets,
    }

    local function tick(now)
        local now, on_screen, from_start, to_end = play_state.get(now)
        if not on_screen and not img then
            img = {}
            for idx = 1, #assets do
                img[idx] = resource.load_image{
                    file = assets[idx].asset.file.asset_name:copy(),
                }
            end
        elseif on_screen then
            for idx = 1, #assets do
                img[idx]:draw(
                    assets[idx].x1, assets[idx].y1,
                    assets[idx].x2, assets[idx].y2
                )
            end
        end
    end

    return {
        tick = tick;
    }
end


local function Video(play_state, config)
    local vid

    local assets = select_lod_assets{
        max_lod = 3, -- support up to 6K (=3x3 FullHD)
        max_assets = 1, -- we only want to select a single video
        assets = config.assets,
    }

    local function tick(now)
        local now, on_screen, from_start, to_end = play_state.get(now)
        if not on_screen and not vid then
            vid = {}
            for idx = 1, #assets do
                vid[idx] = resource.load_video{
                    file = assets[idx].asset.file.asset_name:copy(),
                    raw = true,
                    looped = true, -- XXX: not sure about this one
                                   -- it might result in the first frame
                                   -- being visible briefly, is switching to
                                   -- the next content happens slightly too
                                   -- late.
                    paused = true,
                }
            end
        elseif on_screen then
            for idx = 1, #assets do
                screen.video(
                    vid[idx],
                    assets[idx].x1, assets[idx].y1,
                    assets[idx].x2, assets[idx].y2,
                    1
                ):start()
            end
        end
    end

    local function cleanup()
        if vid then
            for idx = 1, #assets do
                vid[idx]:layer(-1):place(-1, -1, -1, -1):dispose()
            end
        end
    end

    return {
        tick = tick;
        cleanup = cleanup;
    }
end


local product_slot = SlotLoader "product"

local function Product(play_state, item)
    local product, product_assets
    local product_image, brand_image, qrcode_image
    local price, old_price
    local artnr, name = '', ''
    local matching_products = {}
    local active_revision = nil
    local pending_bundle = nil
    local pending_revision = nil
    local last_poll_at = 0
    local next_swap_at = play_state.get_start()

    local function read_slot(now, on_screen)
        local first_try = play_state.get_start()-1
        local second_try = now
        if on_screen then
            first_try, second_try = now, play_state.get_start()-1
        end
        local slot, slot_assets = product_slot(first_try, item.uuid)
        if not slot then
            slot, slot_assets = product_slot(second_try, item.uuid)
        end
        return slot, slot_assets
    end

    local function load_bundle(slot, slot_assets)
        local bundle = {
            product = slot,
            product_assets = slot_assets,
            product_image = slot_assets.load_image(slot.img_product),
            brand_image = slot_assets.load_image(slot.img_brand),
            qrcode_image = slot_assets.load_image(slot.img_qrcode),
            matching_products = {},
            price = nil,
            old_price = nil,
            artnr = "",
            name = "",
        }

        if slot.current_price then
            bundle.price = helper.format_price(slot.currency, slot.current_price)
        end
        if slot.original_price then
            bundle.old_price = helper.format_price(slot.currency, slot.original_price)
        end
        bundle.artnr = T('detail_view_sku_label') .. ' ' .. slot.id

        local translation_prefix
        if slot.customer_group == "MALE" then
            translation_prefix = "webcat_haka_singular_"
        else
            translation_prefix = "webcat_singular_"
        end
        bundle.name = T(
            translation_prefix .. slot.web_category:gsub(" ", "_"):lower(),
            slot.web_category
        )

        for idx = 1, #(slot.matching or {}) do
            local matching = slot.matching[idx]
            bundle.matching_products[#bundle.matching_products+1] = {
                image = slot_assets.load_image(matching.img_product),
                price = matching.current_price and helper.format_price_no_currency(
                    slot.currency, matching.current_price
                ),
            }
        end
        return bundle
    end

    local function apply_bundle(bundle, revision, now)
        product = bundle.product
        product_assets = bundle.product_assets
        product_image = bundle.product_image
        brand_image = bundle.brand_image
        qrcode_image = bundle.qrcode_image
        matching_products = bundle.matching_products
        price = bundle.price
        old_price = bundle.old_price
        artnr = bundle.artnr
        name = bundle.name
        active_revision = revision
        pending_bundle = nil
        pending_revision = nil
        next_swap_at = now + item.duration

        debug_global_line_1 = string.format(
            "product id=%s variant=%s mode=%s",
            tostring(product.id or "?"),
            tostring(product.variant_id or "?"),
            tostring(product.debug_mode or "?")
        )
    end

    local function poll_slot(now, on_screen)
        local slot, slot_assets = read_slot(now, on_screen)
        if not slot then
            return
        end
        local revision = table.concat({
            tostring(slot.id or ""),
            tostring(slot.variant_id or ""),
            tostring(slot.debug_updated_at or ""),
        }, "|")
        if revision == active_revision or revision == pending_revision then
            return
        end
        pending_bundle = load_bundle(slot, slot_assets)
        pending_revision = revision
    end

    local function tick(now)
        local now, on_screen, from_start, to_end = play_state.get(now)
        if from_start >= -2 and (now - last_poll_at >= 1) then
            last_poll_at = now
            poll_slot(now, on_screen)
        end

        if pending_bundle and not product then
            apply_bundle(pending_bundle, pending_revision, now)
        elseif pending_bundle and now >= next_swap_at then
            apply_bundle(pending_bundle, pending_revision, now)
        end

        if on_screen and product then
            local remaining = math.max(0, math.floor(next_swap_at - now))
            debug_global_line_2 = string.format(
                "state=%s wait=%ss t=%s",
                pending_bundle and "pending" or "stable",
                tostring(remaining),
                os.date("%H:%M:%S")
            )
            local function price_box(x, y)
                if testing() then
                    local foo = (math.floor(sys.now())) % 3
                    if foo == 0 then
                        price = "123.4€"
                        old_price = "333.40€"
                    elseif foo == 1 then
                        price = "4444.33€"
                        old_price = nil
                    else
                        price = nil
                        old_price = nil
                    end
                end

                local x_right = x+660
                local x_left

                local function render_price(price, y)
                    local size = 80
                    local margin = 20
                    local w = ny_assets.font.bold:width(price, size) + 2*margin
                    ny_assets.pi.black:draw(x_right-w, y, x_right, y+140)
                    ny_assets.font.bold:write(x_right-w+margin, y+30, price, size, 1,1,1,1)
                    return w
                end

                local function render_old_price(y)
                    local size = 40
                    local w = ny_assets.font.regl:write(x_left, y, old_price, size, 0,0,0,1)
                    ny_assets.pi.black:draw(x_left, y+size/2-2, x_left+w, y+size/2+2, 0.8)
                end

                local function render_art_nr(y)
                    local size = 30
                    local w = ny_assets.font.regl:width(artnr, size)
                    ny_assets.font.regl:write(x_right-w, y, artnr, size, 0,0,0,1)
                    return w
                end

                local function render_name(y)
                    local size = 45
                    local w = ny_assets.font.regl:width(name, size)
                    if x_left + w < x_right then
                        -- left align on price box
                        ny_assets.font.regl:write(x_left, y, name, size, 0,0,0,1)
                    else
                        -- right align to right price box edge
                        ny_assets.font.regl:write(x_right-w, y, name, size, 0,0,0,1)
                    end
                end

                ny_assets.pi.price_overlay:draw(x, y, x+745, y+416, 0.9)

                if price and old_price then
                    x_left = x_right - render_price(price, y+135)
                    render_old_price(y+80)
                    render_art_nr(y+310)
                    render_name(y+30)
                elseif price then
                    x_left = x_right - render_price(price, y+115)
                    render_art_nr(y+295)
                    render_name(y+32)
                else
                    x_left = x_right - render_price("COMING SOON", y+115)
                    render_art_nr(y+295)
                    render_name(y+32)
                end
            end

            local function matching_box(x, y)
                helper.centered_text(ny_assets.font.bold, x+960, y+10, "COMPLETE YOUR LOOK", 60, .2,.2,.2,1)
                ny_assets.pi.matching_box:draw(x+50, y+80, x+1920, y+1070)

                local margin = 60
                local product_w = 500
                local product_h = 700
                local img_padding = 20
                local price_size = 40

                local px = x+960 - (#matching_products*(product_w+margin))/2
                local py = y+180

                for idx = 1, #matching_products do
                    local matching_product = matching_products[idx]
                    ny_assets.pi.gradient:draw(px+margin/2, py, px+margin/2+product_w, py+product_h)
                    util.draw_correct(matching_product.image, 
                        px+margin/2+img_padding, py+img_padding,
                        px+margin/2+product_w-img_padding, py+product_h-img_padding
                    )

                    if matching_product.price then
                        local font = ny_assets.font.bold
                        local cx = px+margin/2+product_w/2
                        local w = font:width(matching_product.price, price_size) + 10 +
                                  font:width(product.currency, price_size*0.7)
                        local price_x = cx - w/2
                        local price_y = py + product_h + 20
                        local price_w = font:write(price_x, price_y, matching_product.price, price_size, .2,.2,.2,1)
                        price_x = price_x + price_w + 10
                        font:write(price_x, price_y+price_size*0.3, product.currency, price_size*0.7, .2,.2,.2,1)
                    else
                        local font = ny_assets.font.regl
                        local cx = px+margin/2+product_w/2
                        local y = py + product_h + 20
                        helper.centered_text(font, cx, y, "COMING SOON", price_size, .2,.2,.2,1)
                    end

                    px = px + product_w + margin
                end
            end

            gl.clear(1,1,1,1)

            if content_area.is_landscape() then
                ny_assets.pi.background:draw(0, 0, 1920, 2160)
                helper.img_centered(brand_image, 2900, 420,  1000, 500)
                helper.img_centered(product_image, 1050, 1100, 1650, 1650)
                qrcode_image:draw(40, 40, 320, 320)
                price_box(0, 1417)

                if #matching_products > 0 then
                    matching_box(1920, 1080)
                end
            else
                ny_assets.pi.background:draw(0, HEIGHT/2, WIDTH, HEIGHT)
                helper.img_centered(brand_image, 1780, 200,  500, 380)
                helper.img_centered(product_image, 1080, 1250, 1900, 1700)
                qrcode_image:draw(40, 40, 320, 320)
                price_box(0, 1500)

                if #matching_products > 0 then
                    matching_box(120, 2450)
                end
            end
        elseif on_screen then
            debug_global_line_2 = "state=waiting_payload t=" .. os.date("%H:%M:%S")
            ny_assets.fallback:draw(0, 0, WIDTH, HEIGHT)
        end
    end

    return {
        tick = tick;
    }
end

local lifestyle_slot = SlotLoader "lifestyle"

local function Lifestyle(play_state, item)
    local lifestyles

    local category_size = 50
    local headline_size = 100
    local text_size = 56
    local margin = 50
    local box_width = choice(content_area.is_landscape(), 1300, 1800)

    local function tick(now)
        local now, on_screen, from_start, to_end = play_state.get(now)
        if not on_screen then
            if not lifestyles and from_start >= -2 then
                local pinned_time = play_state.get_start()-1
                local posts, slot_assets = lifestyle_slot(pinned_time, item.uuid)
                if not posts then
                    return
                end

                local loaded_lifestyles = {}
                for idx = 1, #posts do
                    local post = posts[idx]
                    loaded_lifestyles[#loaded_lifestyles+1] = {
                        background = slot_assets.load_image(post.img_background),
                        qrcode = slot_assets.load_image(post.img_qrcode),
                        category = post.category,
                        wrapped_headline = helper.wrap(
                            post.headline, ny_assets.font.bold, headline_size, box_width
                        ),
                        wrapped_text = helper.wrap(
                            post.text, ny_assets.font.thin, text_size, box_width
                        )
                    }
                end
                lifestyles = loaded_lifestyles
            end
        elseif lifestyles then
            local function stylebox(post, cx, y, margin)
                local height
                while true do
                    height = (
                        #post.wrapped_text * text_size +
                        margin +
                        #post.wrapped_headline * headline_size +
                        3*margin +
                        category_size
                    )
                    if height < 750 then
                        -- acceptable height
                        break
                    elseif margin > 10 then
                        -- try to shrink margin
                        margin = margin - 10
                    elseif #post.wrapped_text > 3 then
                        -- try to strip the text
                        post.wrapped_text[#post.wrapped_text] = nil
                        post.wrapped_text[#post.wrapped_text] = post.wrapped_text[#post.wrapped_text] .. "..."
                    else
                        -- well. nothing we can do. render anyway
                        break
                    end
                end

                local function add_line(font, text, size)
                    helper.centered_text(font, cx, y, text, size, 0,0,0,1)
                    y = y + size
                end

                add_line(ny_assets.font.regl, post.category, category_size)
                y = y + margin
                for i = 1, #post.wrapped_headline do
                    add_line(ny_assets.font.bold, post.wrapped_headline[i], headline_size)
                end
                y = y + 3*margin
                for i = 1, #post.wrapped_text do
                    add_line(ny_assets.font.thin, post.wrapped_text[i], text_size)
                end
            end

            gl.clear(1,1,1,1)

            if content_area.is_landscape() then
                local first = lifestyles[1]
                if first then
                    first.background:draw(0, 0, 2400, 1058)
                    stylebox(first, 3110, 50, margin)
                    first.qrcode:draw(WIDTH-300, 1080-300, WIDTH, 1080)
                    ny_assets.sty.logo:draw(2440, 1080-280, 2440+280, 1060)
                end

                local second = lifestyles[2]
                if second then
                    second.background:draw(1440, 1102, 3840, 2160)
                    stylebox(second, 680, 1150, margin)
                    second.qrcode:draw(0, HEIGHT-300, 300, HEIGHT)
                    ny_assets.sty.logo:draw(1400-280, HEIGHT-280, 1400, HEIGHT-20)
                end
            else
                local first = lifestyles[1]
                if first then
                    first.background:draw(65, 855, 2095, 1740)
                    stylebox(first, 1080, 50, margin)
                    -- first.qrcode:draw(WIDTH-300, 1080-300, WIDTH, 1080)
                    -- ny_assets.sty.logo:draw(2440, 1080-280, 2440+280, 1060)
                end

                local second = lifestyles[2]
                if second then
                    second.background:draw(65, 2630, 2095, 3615)
                    stylebox(second, 1080, 2000, margin)
                    -- second.qrcode:draw(0, HEIGHT-300, 300, HEIGHT)
                    -- ny_assets.sty.logo:draw(1400-280, HEIGHT-280, 1400, HEIGHT-20)
                end
            end
        else
            ny_assets.fallback:draw(0, 0, WIDTH, HEIGHT)
        end
    end

    return {
        tick = tick,
    }
end

local dressfm_slot = SlotLoader "dressfm"

local function DressFM(play_state, item)
    local song, song_assets
    local cover_image

    local function tick(now)
        local now, on_screen, from_start, to_end = play_state.get(now)
        if not on_screen then
            if not song and from_start >= -2 then
                local pinned_time = play_state.get_start()-1
                song, song_assets = dressfm_slot(pinned_time, item.uuid)
                if not song then
                    return
                end

                cover_image = song_assets.load_image(song.img_cover)
            end
        elseif song then
            gl.clear(1,1,1,1)
            cover_image:draw(100, 100, 1000, 1000)
            helper.centered_text(ny_assets.font.thin, WIDTH/2, 1000, song.artist, 40, .2,.2,.2,1)
            helper.centered_text(ny_assets.font.thin, WIDTH/2, 1040, song.title, 40, .2,.2,.2,1)
        else
            ny_assets.fallback:draw(0, 0, WIDTH, HEIGHT)
        end
    end

    return {
        tick = tick;
    }
end

local function Playlist()
    local total_duration = 0
    local playlist
    local cur, nxt

    local function update(new_playlist)
        playlist = new_playlist or {}
        if #playlist == 0 then
            playlist = {{
                type = "image",
                duration = 5,
                assets = {{
                    file = {
                        asset_name = "empty.png",
                    }
                }}
            }}
        end
        total_duration = 0
        for idx = 1, #playlist do
            local item = playlist[idx]
            if item.duration < 5 then
                item.duration = 5
            end
            item.offset = total_duration
            if not item.uuid or #item.uuid == 0 then
                item.uuid = string.format('slot-%d', idx)
            end
            item.assets = item.assets or {}
            for a = 1, #item.assets do
                local file = item.assets[a].file
                file.asset_name = resource.open_file(file.asset_name)
            end
            total_duration = total_duration + item.duration
        end
        print("total playlist duration", total_duration)

        -- If item identity changed, rebuild handlers on next tick.
        if cur and #playlist == 1 then
            if cur.item_type ~= playlist[1].type or cur.item_uuid ~= playlist[1].uuid then
                if cur.handler.cleanup then
                    cur.handler.cleanup()
                end
                cur, nxt = nil, nil
            end
        end
    end

    local function get_next_item(now, min_time_to_start)
        local epoch_offset = now % total_duration
        local epoch_start = now - epoch_offset
        local min_start_t, next_idx = 999999999999999999
        for idx = 1, #playlist do
            local item = playlist[idx]
            local start_t = epoch_start + item.offset
            if start_t - min_time_to_start < now then
                start_t = start_t + total_duration
            end
            if start_t < min_start_t then
                min_start_t, next_idx = start_t, idx
            end
        end
        assert(next_idx)
        return min_start_t, playlist[next_idx]
    end

    local function prepare_next(now, min_time_to_start)
        local start_t, item = get_next_item(now, min_time_to_start)
        local play_state = PlayState(start_t, item.duration)
        return {
            play_state = play_state,
            item_type = item.type,
            item_uuid = item.uuid,
            handler = ({
                image = Image,
                video = Video,
                product = Product,
                lifestyle = Lifestyle,
                dressfm = DressFM,
            })[item.type](play_state, item)
        }
    end

    local function play(now)
        if cur and #playlist == 1 and
           cur.item_type == playlist[1].type and
           cur.item_uuid == playlist[1].uuid then
            cur.handler.tick(now)
            return
        end

        if not nxt then
            local min_time_to_start = 1
            if cur then
                min_time_to_start = cur.play_state.get_earliest_end() - now

                -- Allow 0.25 second window. In an unchanged playlist this
                -- ensures that the next piece of content is always found,
                -- even if floating point rounding errors slightly mess with
                -- the times.
                --
                -- For a playlist that is modified, we might cut of the
                -- current content 0.25 seconds earlier than configured.
                -- This is probably not noticeable.
                min_time_to_start = min_time_to_start - 0.25
            end
            nxt = prepare_next(now, min_time_to_start)
        end
        if cur then
            cur.play_state.set_end(nxt.play_state.get_start())
        end
        if now >= nxt.play_state.get_start() then
            if cur and cur.handler.cleanup then
                cur.handler.cleanup()
            end
            cur, nxt = nxt, nil
            node.gc()
        end

        if nxt then nxt.handler.tick(now) end
        if cur then cur.handler.tick(now) end
    end

    return {
        update = update;
        play = play;
    }
end
local playlist = Playlist()
local debug_overlay_enabled = false
local debug_overlay_root = false
local debug_global_line_1 = ""
local debug_global_line_2 = ""

local function is_enabled(value)
    if value == true then
        return true
    end
    if type(value) == "number" then
        return value ~= 0
    end
    if type(value) == "string" then
        local lower = value:lower()
        return lower == "true" or lower == "1" or lower == "yes" or lower == "on"
    end
    return false
end

local function update_debug_overlay_state()
    debug_overlay_enabled = debug_overlay_root
end


util.json_watch("config.json", function(config)
    playlist.update(config.playlist)
    debug_overlay_root = is_enabled(config.debug_overlay)
    update_debug_overlay_state()
end)

util.json_watch("screen/config.json", function(config)
    content_area.update(config.orientation == "landscape")

    local function setup_videowall(width, height, n_th_screen, landscape)
        local x = math.fmod((n_th_screen-1), width)
        local y = math.floor((n_th_screen-1) / width)

        local w, h = content_area.size()
        w = w / width
        h = h / height

        if landscape then
            screen.update({
                x = x*w, y = y*h, w = w, h = h, rotation = 0
            }, content_area.size())
        else
            screen.update({
                x = (x+1)*w, y = y*h, w = h, h = w, rotation = 90
            }, content_area.size())
        end
    end

    local function setup_videowall_outwards(n_th_screen)
        local x = math.fmod((n_th_screen-1), 2)
        local y = math.floor((n_th_screen-1) / 2)

        local w, h = content_area.size()
        w = w / 2
        h = h / 2

        if math.fmod(n_th_screen-1, 2) == 0 then
            screen.update({
                x = x*w, y = (y+1)*h, w = h, h = w, rotation = 270
            }, content_area.size())
        else
            screen.update({
                x = (x+1)*w, y = y*h, w = h, h = w, rotation = 90
            }, content_area.size())
        end
    end

    local function setup_device(arrangement, nth_screen)
        local w, h = content_area.size()
        if arrangement == "default" then
            if content_area.is_landscape() then
                screen.update({
                    x = 0, y = 0, w = w, h = h, rotation = 0
                }, content_area.size())
            else
                screen.update({
                    x = w, y = 0, w = h, h = w, rotation = 90,
                }, content_area.size())
            end
        elseif arrangement == "flipped" then
            if content_area.is_landscape() then
                screen.update({
                    x = w, y = h, w = w, h = h, rotation = 180
                }, content_area.size())
            else
                screen.update({
                    x = 0, y = h, w = h, h = w, rotation = 270,
                }, content_area.size())
            end
        elseif arrangement == "2x2wall" then
            setup_videowall(2, 2, nth_screen, content_area.is_landscape())
        elseif arrangement == "2x2wall-outwards" then
            setup_videowall_outwards(nth_screen)
        elseif arrangement == "3x3wall" then
            setup_videowall(3, 3, nth_screen, content_area.is_landscape())
        end
    end

    local configured = false
    for s = 1, #config.screens do
        local screen = config.screens[s]
        for d = 1, #screen.devices do
            local device = screen.devices[d]
            if device.serial == sys.get_env "SERIAL" then
                time.set_offset(screen.offset)
                setup_device(screen.arrangement, d)
                configured = true
            end
        end
    end
    if not configured then
        time.set_offset(0)
        setup_device("default", 1)
    end
end)


local test_assets = {
    red = resource.create_colored_texture(1,0,0,1),
    font = resource.load_font "default-font.ttf",
}

function node.render()
    screen.setup()
    playlist.play(time.get())

    if debug_overlay_enabled then
        gl.ortho()
        local line1 = debug_global_line_1 ~= "" and debug_global_line_1 or "dbg active (waiting for product)"
        local line2 = debug_global_line_2 ~= "" and debug_global_line_2 or ("time=" .. os.date("%Y-%m-%d %H:%M:%S"))
        local y = NATIVE_HEIGHT - 58
        test_assets.red:draw(0, NATIVE_HEIGHT - 66, NATIVE_WIDTH, NATIVE_HEIGHT, 0.35)
        test_assets.font:write(8, y, line1, 20, 1,1,1,1)
        test_assets.font:write(8, y+22, line2, 20, 1,1,1,1)
    end

    if testing() then
        gl.ortho()
        test_assets.red:draw(NATIVE_WIDTH-200, 0, NATIVE_WIDTH, 60, 0.5)
        test_assets.font:write(NATIVE_WIDTH-190, 5, 'Testmode active', 20, 1,1,1,min(1, 1-math.sin(sys.now()*3)))
        test_assets.font:write(NATIVE_WIDTH-190, 30, 'Serial: ' .. sys.get_env("SERIAL"), 20, 1,1,1,1)
    end
end

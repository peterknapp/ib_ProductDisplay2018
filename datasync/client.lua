local PREFIX = 'datasync/'

local json = require 'json'

local function SyncedData(key)
    local index = {}

    local function handle_new_index(new_index)
        for idx = 1, #new_index do
            local version = new_index[idx]
            for filename, versioned_file in pairs(version.files) do
                version.files[filename] = resource.open_file(
                    PREFIX .. versioned_file
                )
            end
        end
        index = new_index
        print("updated key", key)
    end

    local function file_at(timestamp, filename)
        local active_idx
        for idx = #index, 1, -1 do
            local version = index[idx]
            if version.commit_time <= timestamp then
                active_idx = idx
                break
            end
        end
        if not active_idx then
            return nil
        end
        local version = index[active_idx]
        local file = version.files[filename]
        if not file then
            return nil
        end
        return file:copy()
    end

    local function json_at(...)
        local file = file_at(...)
        if not file then
            return nil
        end
        return json.decode(resource.load_file(file))
    end

    util.json_watch(PREFIX .. key .. '.json', handle_new_index)

    return {
        file_at = file_at;
        json_at = json_at;
    }
end

return {
    SyncedData = SyncedData;
}

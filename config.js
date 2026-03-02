'use strict';

// For some reason sortable.js doesn't properly
// work in chrome 62 without using the forceFallback
// option :-\
var isChrome = !!window.chrome;

const store = new Vuex.Store({
  strict: true,
  state: {
    options: {},
    assets: [],
    brands: {},
    config: {
      playlist: [],
    },
  },
  mutations: {
    init(state, {nodejson, brands, assets, config}) {
      var by_filename = {};
      for (var asset_id in assets) {
        var asset = assets[asset_id];
        if (asset.filetype != 'image' &&
            asset.filetype != 'video')
          continue;
        by_filename[asset.filename] = asset;
        asset.lod = {
          '2x2': [0, 0, 0, 0],
          '3x3': [0, 0, 0, 0, 0, 0, 0, 0, 0],
        }
      }

      var assignable_assets = {};

      for (var filename in by_filename) {
        var asset = by_filename[filename];
        var m = asset.filename.match(/^(.*)-(2x2|3x3)-(\d)([.].*)$/);
        if (m) {
          var base_filename = m[1] + m[4];
          var base_asset = by_filename[base_filename];
          if (!base_asset)
            continue;
          var lod = m[2];
          var idx = parseInt(m[3]);
          base_asset.lod[lod][idx] = asset.id;
          continue;
        }
        assignable_assets[asset.id] = asset;
      }

      for (var asset_id in assignable_assets) {
        var asset = assignable_assets[asset_id];
        asset.ready = {
          '2x2': asset.lod['2x2'].every((asset_id) => asset_id > 0),
          '3x3': asset.lod['3x3'].every((asset_id) => asset_id > 0),
        }

        if (asset.ready['3x3']) {
          asset.quality = '6K';
        } else if (asset.ready['2x2']) {
          asset.quality = '4K';
        } else {
          asset.quality = 'FullHD';
        }

        var w = asset.metadata.width;
        var h = asset.metadata.height;
        var asset_aspect = w/h;
        var known_aspects = {
          '16:9': 16/9,
          '9:16': 9/16,
          '4:3': 4/3,
          '3:4': 3/4,
        }
        asset.aspect = 'odd';
        for (var name in known_aspects) {
          var aspect = known_aspects[name];
          if (Math.abs(aspect - asset_aspect) < 0.2) {
            asset.aspect = name;
            break;
          }
        }
      }

      assignable_assets['product'] = {
        special: 'Produktinformation Seite',
        filetype: 'product',
        filename: '__product',
        thumb: 'thumb-product.png',
        aspect: 'all',
        quality: '4K',
      }

      assignable_assets['lifestyle'] = {
        special: 'Lifestyle Seite',
        filetype: 'lifestyle',
        filename: '__lifestyle',
        thumb: 'thumb-lifestyle.png',
        aspect: 'all',
        quality: '4K',
      }

      assignable_assets['dressfm'] = {
        special: 'DressFM Seite',
        filetype: 'dressfm',
        filename: '__dressfm',
        thumb: 'thumb-dressfm.png',
        aspect: 'all',
        quality: '4K',
      }

      state.assets = assignable_assets;

      // fix old setup configurations: add missing uuids
      for (var idx in config.playlist) {
        var item = config.playlist[idx];
        if (!item.uuid) {
          item.uuid = uuid()
        }
      }

      state.config = config;
      state.brands = brands;

      var options = {}
      for (var idx in nodejson.options) {
        var option = nodejson.options[idx];
        options[option.name] = option;
      }
      state.options = options;
    },
    update_playlist(state, {playlist}) {
      Vue.set(state.config, 'playlist', playlist);
    },
    update_item_setting(state, {item_id, key, value}) {
      Vue.set(state.config.playlist[item_id].settings, key, value);
    },
    update_item_duration(state, {item_id, duration}) {
      Vue.set(state.config.playlist[item_id], 'duration', duration);
    },
    append_asset(state, {asset}) {
      state.config.playlist.push(asset);
    },
    delete_playlist_item(state, {item_id}) {
      state.config.playlist.splice(item_id, 1);
    },
    set_value(state, {key, value}) {
      Vue.set(state.config, key, value);
    },
  }
})

Vue.filter('trunc', function(value, max_len) {
  if (value.length <= max_len)
    return value;
  var shrink = value.length - max_len + 4;
  var m = value.match(/^(.*)([.][^.]+)$/);
  if (m) {
    var prefix = m[1].substr(0, m[1].length - shrink);
    var suffix = m[2];
    return prefix + '[..]' + suffix;
  }
  return value.substr(0, max_len);
})

Vue.component('config-ui', {
  template: '#config-ui',
  computed: {
  }
})

function uuid() {
  var uuid = "", i, random;
  for (i = 0; i < 32; i++) {
    random = Math.random() * 16 | 0;

    if (i == 8 || i == 12 || i == 16 || i == 20) {
      uuid += "-"
    }
    uuid += (i == 12 ? 4 : (i == 16 ? (random & 3 | 8) : random)).toString(16);
  }
  return uuid;
}

function convert_to_playlist_item(asset) {
  var type = asset.filetype;
  if (type == 'product') {
    return {
      type: 'product',
      duration: 10,
      settings: {
        mode: 'random_product',
        brands: [],
      },
      assets: [],
      uuid: uuid(),
    }
  } else if (type == 'lifestyle') {
    return {
      type: 'lifestyle',
      duration: 10,
      settings: {},
      assets: [],
      uuid: uuid(),
    }
  } else if (type == 'dressfm') {
    return {
      type: 'dressfm',
      duration: 10,
      settings: {},
      assets: [],
      uuid: uuid(),
    }
  }

  var assets = [{
    file: asset.id,
  }]
  var lods = ['2x2', '3x3'];
  for (var idx in lods) {
    var lod = lods[idx];
    if (asset.ready[lod]) {
      for (var idx in asset.lod[lod]) {
        console.log(lod);
        var asset_id = asset.lod[lod][idx];
        assets.push({
          file: asset_id,
        })
      }
    }
  }

  var duration = 10;
  if (type == 'video')
    duration = asset.metadata.duration;

  return {
    type: type,
    duration: duration,
    settings: {},
    assets: assets,
    uuid: uuid(),
  }
}

Vue.component('playlist-editor', {
  template: '#playlist-editor',
  data: () => ({
    playlist_dd_options: {
      forceFallback: isChrome,
      handle: '.handle',
      group: {
        name: 'page-list',
        pull: true,
        put: ['page-list', 'asset-list'],
      }
    },
  }),
  computed: {
    playlist: {
      get() {
        return this.$store.state.config.playlist;
      },
      set(playlist) {
        for (var idx in playlist) {
          var item = playlist[idx];
          // it's a dropped asset. convert to playlist item
          if (item.filetype) {
            playlist[idx] = convert_to_playlist_item(item);
          }
        }
        this.$store.commit('update_playlist', {
          playlist: playlist,
        })
      },
    }
  }
})

function config_value(key, default_value) {
  return {
    get() {
      var value = this.$store.state.config[key];
      if (value == undefined)
        value = default_value;
      return value;
    },
    set(v) {
      this.$store.commit('set_value', {
        key: key,
        value: v,
      })
    }
  }
}

function values_from_nodejson(key) {
  return {
    get() {
      var options = [];
      var values = this.$store.state.options[key];
      if (!values) // might not be loaded yet
        return [];
      for (var idx in values.options) {
        var pair = values.options[idx];
        options.push({
          k: pair[0],
          v: pair[1],
        })
      }
      return options;
    }
  }
}

Vue.component('global-settings', {
  template: '#global-settings',
  computed: {
    endpoint: config_value('endpoint', 'api.newyorker.de'),
    country: config_value('country', 'de'),
    language: config_value('language', 'de'),

    endpoint_values: values_from_nodejson('endpoint'),
    country_values: values_from_nodejson('country'),
    language_values: values_from_nodejson('language'),
  },
})

Vue.component('playlist-item', {
  template: '#playlist-item',
  props: ['item_id'],
  computed: {
    assets() {
      return this.$store.state.assets;
    },
    item() {
      return this.$store.state.config.playlist[this.item_id];
    },
    base_asset() {
      return this.assets[this.item.assets[0].file];
    },
  },
  methods: {
    onDelete(e) {
      this.$store.commit('delete_playlist_item', {
        item_id: this.item_id,
      })
    }
  }
})

Vue.component('item-duration', {
  template: '#item-duration',
  props: ['item_id'],
  data: () => ({
    invalid: false,
  }),
  computed: {
    item() {
      return this.$store.state.config.playlist[this.item_id];
    },
    default_duration() {
      return Math.floor(42.23);
    },
    duration: {
      get() {
        return this.item.duration;
      },
      set(v) {
        var duration = parseFloat(v);
        if (isNaN(duration)) {
          this.invalid = true;
          return;
        }
        if (duration < 5) {
          this.invalid = true;
          return;
        }
        this.invalid = false;
        this.$store.commit('update_item_duration', {
          item_id: this.item_id,
          duration: duration,
        })
      }
    },
  },
})

function key_value(key, default_value) {
  return {
    get() {
      var value = this.settings[key];
      if (value == undefined)
        value = default_value;
      return value;
    },
    set(v) {
      console.log('setting', key, 'to', v);
      this.$store.commit('update_item_setting', {
        item_id: this.item_id,
        key: key,
        value: v,
      })
    }
  }
}

Vue.component('product-info', {
  template: '#product-info',
  props: ['item_id'],
  computed: {
    config() {
      return this.$store.state.config;
    },
    item() {
      return this.config.playlist[this.item_id];
    },
    settings() {
      return this.item.settings;
    },
    product_url() {
      return 'https://app.newyorker.de/share/product/' + 
        this.product_id + '/' + this.variant_id +
        '?country=' + this.config.country;
    },
    brand_options() {
      var brands = [];
      for (var brand in this.$store.state.brands) {
        brands.push(brand);
      }
      brands.sort()
      return brands;
    },
    gender: key_value('gender', 'female'),
    mode: key_value('mode', 'random_product'),
    product_id: key_value('product_id', ''),
    variant_id: key_value('variant_id', '001'),
    brands: key_value('brands', []),
  },
})

Vue.component('lifestyle-info', {
  template: '#lifestyle-info',
  props: ['item_id'],
})

Vue.component('dressfm-info', {
  template: '#dressfm-info',
  props: ['item_id'],
  computed: {
    config() {
      return this.$store.state.config;
    },
    item() {
      return this.config.playlist[this.item_id];
    },
    settings() {
      return this.item.settings;
    },
    stream: key_value('stream', 'nyir-ger'),
  }
})

Vue.component('asset-list', {
  template: '#asset-list',
  data: () => ({
    sorted: "filename",
    filter_type: "all",
    filter_aspect: "all",
    search: "",
    asset_dd_options: {
      forceFallback: isChrome,
      group: {
        name: 'asset-list',
        pull: 'clone',
        put: false,
      }
    },
  }),
  computed: {
    assets() {
      var result = [];
      var assets = this.$store.state.assets
      var tokens = this.search.split(" ");
      for (var idx in assets) {
        var asset = assets[idx];
        if (this.filter_type != "all" &&
            asset.filetype != this.filter_type)
          continue;
        if (this.filter_aspect != "all" &&
            asset.aspect != "all" &&
            asset.aspect != this.filter_aspect)
          continue;
        var doc = (
          asset.filename + ' ' + asset.filetype + ' ' +
          asset.aspect + ' ' + asset.quality + ' ' +
          asset.special
        ).toLocaleLowerCase();
        var found = false;
        for (var t in tokens) {
          var token = tokens[t];
          if (doc.indexOf(token) != -1) {
            found = true;
            break
          }
        }
        if (found)
          result.push(asset)
      }
      result.sort({
        filename: (a, b) => {
          var fa = a.filename.toLocaleLowerCase();
          var fb = b.filename.toLocaleLowerCase();
          return fa.localeCompare(fb)
        },
        upload: (a, b) => {
          return b.uploaded - a.uploaded
        },
      }[this.sorted]);
      return result
    }
  },
  methods: {
    onSearch(query) {
      this.search = query.toLocaleLowerCase();
    },
    onAppend(asset) {
      this.$store.commit('append_asset', {
        asset: convert_to_playlist_item(asset),
      })
    },
  },
})

const app = new Vue({
  el: "#app",
  store,
})

function load_async(url) {
  return new Promise(function(resolve, reject) {
    var xmlhttp = new XMLHttpRequest();
    xmlhttp.onreadystatechange = function() {
      if (xmlhttp.readyState == XMLHttpRequest.DONE) {
        if (xmlhttp.status == 200) {
          resolve(JSON.parse(xmlhttp.responseText))
        } else {
          alert('something else other than 200 was returned');
        }
      }
    };
    xmlhttp.open("GET", url, true);
    xmlhttp.send();
  })
}

ib.setDefaultStyle();

Promise.all([
  ib.ready,

  // Load for possible configuration values.
  load_async("node.json"),

  // fetches the available brands from the mapping file
  // in brands/mapping.json. Loading these dynamically
  // ensures that the filterable brands are always up
  // to date and in sync with the visual represenation.
  load_async("brands/mapping.json"),
]).then((results) => {
  var nodejson = results[1];
  var brands = results[2];
  var device_by_id = {};
  for (var i in ib.devices) {
    var device = ib.devices[i];
    device_by_id[device.id] = device;
  }
  store.commit('init', {
    nodejson: nodejson,
    brands: brands,
    assets: ib.assets,
    config: ib.config,
  })
  store.subscribe((mutation, state) => {
    ib.setConfig(state.config);
  })
})

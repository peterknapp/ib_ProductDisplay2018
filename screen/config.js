'use strict';

const store = new Vuex.Store({
  strict: true,
  state: {
    devices: {},
    config: {
      orientation: "landscape",
      screens: [],
    },
  },
  mutations: {
    init(state, {devices, config}) {
      state.devices = devices;
      state.config = config;
    },
    add_group(state) {
      var new_screen = {
        arrangement: "2x2wall",
        name: "",
        offset: 0,
        devices: [],
      };
      state.config.screens.push(new_screen);
    },
    delete_group(state, {group_id}) {
      state.config.screens.splice(group_id, 1);
    },
    set_orientation(state, {orientation}) {
      state.config.orientation = orientation;
    },
    set_arrangement(state, {group_id, arrangement}) {
      state.config.screens[group_id].arrangement = arrangement;
      var max_devices = {
        'default':          1,
        'flipped':          1,
        '2x2wall':          4,
        '2x2wall-outwards': 4,
        '3x3wall':          9,
      }
      state.config.screens[group_id].devices.splice(max_devices[arrangement]);
    },
    set_name(state, {group_id, name}) {
      state.config.screens[group_id].name = name;
    },
    set_offset(state, {group_id, offset}) {
      state.config.screens[group_id].offset = offset;
    },
    assign_device(state, {group_id, idx, serial}) {
      var devices = state.config.screens[group_id].devices;
      while (idx >= devices.length) {
        devices.push({serial: ''});
      } 
      Vue.set(devices, idx, {serial: serial});
    },
  },
  getters: {
    unused_devices: (state) => (except) => {
      var used_devices = {};
      for (var s in state.config.screens) {
        var screen = state.config.screens[s];
        for (var d in screen.devices) {
          var serial = screen.devices[d].serial;
          if (serial != except)
            used_devices[serial] = true;
        }
      }
      var unused_devices = {};
      for (var id in state.devices) {
        var device = state.devices[id];
        if (used_devices[device.serial])
          continue;
        unused_devices[id] = device;
      }
      return unused_devices;
    }
  }
})

Vue.component('config-ui', {
  template: '#config-ui',
  computed: {
    orientation: {
      get() {
        return this.$store.state.config.orientation;
      },
      set(v) {
        this.$store.commit('set_orientation', {
          orientation: v,
        })
      },
    },
  }
})

Vue.component('screen-groups', {
  template: '#screen-groups',
  computed: {
    screens() {
      return this.$store.state.config.screens;
    },
  },
  methods: {
    onAdd() {
      this.$store.commit('add_group');
    }
  }
})

Vue.component('group-editor', {
  template: '#group-editor',
  props: ['group_id'],
  computed: {
    group() {
      return this.$store.state.config.screens[this.group_id];
    },
    orientation() {
      return this.$store.state.config.orientation;
    },
    arrangement: {
      get() {
        return this.group.arrangement;
      },
      set(v) {
        this.$store.commit('set_arrangement', {
          group_id: this.group_id,
          arrangement: v,
        })
      },
    },
    name: {
      get() {
        return this.group.name;
      },
      set(v) {
        this.$store.commit('set_name', {
          group_id: this.group_id,
          name: v,
        })
      },
    },
    offset: {
      get() {
        return this.group.offset;
      },
      set(v) {
        this.$store.commit('set_offset', {
          group_id: this.group_id,
          offset: parseFloat(v),
        })
      },
    },
    arrangements() {
      return [{
        value: 'default',
        name: 'Single Screen',
      }, {
        value: 'flipped',
        name: 'Single Flipped Screen',
      }, {
        value: '2x2wall',
        name: '2x2 Video Wall',
      }, {
        value: '2x2wall-outwards',
        name: '2x2 Video Wall (outwards facing)',
      }, {
        value: '3x3wall',
        name: '3x3 Video Wall',
      }]
    }
  },
  methods: {
    onDelete() {
      this.$store.commit('delete_group', {
        group_id: this.group_id,
      })
    }
  }
})

Vue.component('device-assignment', {
  template: '#device-assignment',
  props: ['group_id', 'idx', 'rotation'],
  computed: {
    group() {
      return this.$store.state.config.screens[this.group_id];
    },
    serial: {
      get() {
        if (this.idx >= this.group.devices.length)
          return '';
        return this.group.devices[this.idx].serial;
      },
      set(v) {
        this.$store.commit('assign_device', {
          group_id: this.group_id,
          idx: this.idx,
          serial: v,
        })
      },
    },
    css() {
      return 'rot-' + this.rotation;
    },
    devices() {
      var assignable = this.$store.getters.unused_devices(this.serial);
      var options = [{
        serial: '',
        description: '<unassigned>',
      }];
      for (var device_id in assignable) {
        var device = assignable[device_id];
        options.push({
          serial: device.serial,
          description: device.description,
        })
      }
      options.sort((a, b) => a.description.localeCompare(b.description))
      return options;
    }
  },
})

const app = new Vue({
  el: "#app",
  store,
})

ib.setDefaultStyle();
ib.ready.then(() => {
  var device_by_id = {};
  for (var i in ib.devices) {
    var device = ib.devices[i];
    device_by_id[device.id] = device;
  }
  store.commit('init', {
    devices: device_by_id,
    config: ib.config,
  })
  store.subscribe((mutation, state) => {
    ib.setConfig(state.config);
  })
})

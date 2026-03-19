Component({
  properties: {
    item: {
      type: Object,
      value: {}
    }
  },
  data: {
    display: {
      title: "Untitled",
      startTime: "-",
      endTime: "-",
      status: "pending"
    }
  },
  observers: {
    item(next) {
      const item = next || {};
      this.setData({
        display: {
          title: item.title || "Untitled",
          startTime: this.formatTime(item.start_time),
          endTime: this.formatTime(item.end_time),
          status: item.status || "pending"
        }
      });
    }
  },
  methods: {
    formatTime(value) {
      if (!value) return "-";
      const date = new Date(value);
      if (Number.isNaN(date.getTime())) return value;
      const y = date.getFullYear();
      const m = `${date.getMonth() + 1}`.padStart(2, "0");
      const d = `${date.getDate()}`.padStart(2, "0");
      const hh = `${date.getHours()}`.padStart(2, "0");
      const mm = `${date.getMinutes()}`.padStart(2, "0");
      return `${y}-${m}-${d} ${hh}:${mm}`;
    }
  }
});

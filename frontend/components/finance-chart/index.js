Component({
  properties: {
    records: {
      type: Array,
      value: []
    },
    chart: {
      type: Object,
      value: {}
    }
  },
  observers: {
    records(list) {
      this.setData({ bars: this.toBars(list || []) });
    }
  },
  data: {
    bars: []
  },
  methods: {
    toBars(records) {
      const categoryTotals = {};
      let total = 0;
      records.forEach((record) => {
        const amount = Number(record.amount || 0);
        if ((record.type || "").toLowerCase() !== "expense" || amount <= 0) return;
        const category = record.category || "other";
        categoryTotals[category] = (categoryTotals[category] || 0) + amount;
        total += amount;
      });
      const raw = Object.keys(categoryTotals)
        .map((name) => ({
          name,
          amount: categoryTotals[name]
        }))
        .sort((a, b) => b.amount - a.amount)
        .slice(0, 6);

      return raw.map((item) => ({
        ...item,
        amountText: Number(item.amount || 0).toFixed(2),
        width: total > 0 ? `${Math.max(8, Math.round((item.amount / total) * 100))}%` : "8%"
      }));
    }
  }
});

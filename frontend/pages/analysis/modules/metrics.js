const PALETTE = ["#20b26c", "#2f7cf6", "#f5a623", "#ff6b6b", "#8b5cf6", "#14b8a6"];

function pad(value) {
  return `${value}`.padStart(2, "0");
}

function parseAmount(value) {
  const amount = Number(value || 0);
  return Number.isFinite(amount) ? amount : 0;
}

function formatCurrency(value) {
  return parseAmount(value).toFixed(2);
}

function getName(item, fallback) {
  return item.creator_nickname || item.creatorName || fallback;
}

function toDate(value) {
  const date = value ? new Date(value) : null;
  return date && !Number.isNaN(date.getTime()) ? date : null;
}

function dayKey(date) {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

function computeSummary(records, schedules, t) {
  const totalExpense = records
    .filter((item) => item.type === "expense")
    .reduce((sum, item) => sum + parseAmount(item.amount), 0);
  const totalIncome = records
    .filter((item) => item.type === "income")
    .reduce((sum, item) => sum + parseAmount(item.amount), 0);
  const netBalance = totalIncome - totalExpense;
  return [
    { label: t("page.summaryExpense"), value: formatCurrency(totalExpense), tone: "mint" },
    { label: t("page.summaryIncome"), value: formatCurrency(totalIncome), tone: "blue" },
    { label: t("page.summaryBalance"), value: formatCurrency(netBalance), tone: netBalance >= 0 ? "gold" : "rose" },
    { label: t("page.summarySchedules"), value: `${schedules.length}`, tone: "ink" }
  ];
}

function computeCategoryBars(records, t) {
  const grouped = {};
  records
    .filter((item) => item.type === "expense")
    .forEach((item) => {
      const key = item.category || t("common.unset");
      grouped[key] = (grouped[key] || 0) + parseAmount(item.amount);
    });
  const items = Object.keys(grouped)
    .map((name) => ({ name, value: grouped[name] }))
    .sort((a, b) => b.value - a.value)
    .slice(0, 5);
  const max = items.reduce((acc, item) => Math.max(acc, item.value), 0) || 1;
  return items.map((item, index) => ({
    name: item.name,
    valueText: formatCurrency(item.value),
    width: `${Math.max(18, (item.value / max) * 100)}%`,
    color: PALETTE[index % PALETTE.length]
  }));
}

function computeWeekdayBars(schedules, t) {
  const labels = [
    t("page.dayMon"),
    t("page.dayTue"),
    t("page.dayWed"),
    t("page.dayThu"),
    t("page.dayFri"),
    t("page.daySat"),
    t("page.daySun")
  ];
  const counts = [0, 0, 0, 0, 0, 0, 0];
  schedules.forEach((item) => {
    const date = toDate(item.start_time || item.created_at);
    if (!date) return;
    const jsDay = date.getDay();
    const index = jsDay === 0 ? 6 : jsDay - 1;
    counts[index] += 1;
  });
  const max = counts.reduce((acc, value) => Math.max(acc, value), 0) || 1;
  return labels.map((label, index) => ({
    label,
    count: counts[index],
    height: `${Math.max(18, (counts[index] / max) * 100)}%`
  }));
}

function computeMemberBars(records, schedules, t) {
  const grouped = {};
  schedules.forEach((item) => {
    const name = getName(item, t("common.teamMember"));
    if (!grouped[name]) {
      grouped[name] = { name, scheduleCount: 0, recordCount: 0 };
    }
    grouped[name].scheduleCount += 1;
  });
  records.forEach((item) => {
    const name = getName(item, t("common.teamMember"));
    if (!grouped[name]) {
      grouped[name] = { name, scheduleCount: 0, recordCount: 0 };
    }
    grouped[name].recordCount += 1;
  });
  const items = Object.keys(grouped)
    .map((name) => ({
      name,
      scheduleCount: grouped[name].scheduleCount,
      recordCount: grouped[name].recordCount,
      total: grouped[name].scheduleCount + grouped[name].recordCount
    }))
    .sort((a, b) => b.total - a.total)
    .slice(0, 5);
  const max = items.reduce((acc, item) => Math.max(acc, item.total), 0) || 1;
  return items.map((item, index) => ({
    name: item.name,
    meta: `${item.scheduleCount} ${t("page.scheduleUnit")} · ${item.recordCount} ${t("page.recordUnit")}`,
    totalText: `${item.total} ${t("page.itemUnit")}`,
    width: `${Math.max(20, (item.total / max) * 100)}%`,
    color: PALETTE[index % PALETTE.length]
  }));
}

function computeRecentExpenseBars(records) {
  const grouped = {};
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  for (let offset = 6; offset >= 0; offset -= 1) {
    const date = new Date(today);
    date.setDate(today.getDate() - offset);
    grouped[dayKey(date)] = 0;
  }
  records
    .filter((item) => item.type === "expense")
    .forEach((item) => {
      const date = toDate(item.occurred_at || item.created_at);
      if (!date) return;
      const key = dayKey(date);
      if (Object.prototype.hasOwnProperty.call(grouped, key)) {
        grouped[key] += parseAmount(item.amount);
      }
    });
  const entries = Object.keys(grouped).map((key) => ({
    key,
    label: key.slice(5),
    value: grouped[key]
  }));
  const max = entries.reduce((acc, item) => Math.max(acc, item.value), 0) || 1;
  return entries.map((item, index) => ({
    label: item.label,
    valueText: formatCurrency(item.value),
    height: `${Math.max(12, (item.value / max) * 100)}%`,
    color: PALETTE[index % PALETTE.length]
  }));
}

function computeTimeBuckets(records, schedules, t) {
  const buckets = [
    { label: t("page.bucketMorning"), count: 0, min: 6, max: 11 },
    { label: t("page.bucketNoon"), count: 0, min: 11, max: 14 },
    { label: t("page.bucketAfternoon"), count: 0, min: 14, max: 18 },
    { label: t("page.bucketEvening"), count: 0, min: 18, max: 23 },
    { label: t("page.bucketNight"), count: 0, min: 23, max: 30 }
  ];

  function addHour(hour) {
    const normalized = hour < 6 ? hour + 24 : hour;
    const bucket = buckets.find((item) => normalized >= item.min && normalized < item.max);
    if (bucket) bucket.count += 1;
  }

  schedules.forEach((item) => {
    const date = toDate(item.start_time || item.created_at);
    if (date) addHour(date.getHours());
  });
  records.forEach((item) => {
    const date = toDate(item.occurred_at || item.created_at);
    if (date) addHour(date.getHours());
  });

  const max = buckets.reduce((acc, item) => Math.max(acc, item.count), 0) || 1;
  return buckets.map((item, index) => ({
    label: item.label,
    countText: `${item.count}`,
    height: `${Math.max(16, (item.count / max) * 100)}%`,
    color: PALETTE[index % PALETTE.length]
  }));
}

function buildAnalysis(records, schedules, t) {
  return {
    summaryCards: computeSummary(records, schedules, t),
    categoryBars: computeCategoryBars(records, t),
    weekdayBars: computeWeekdayBars(schedules, t),
    memberBars: computeMemberBars(records, schedules, t),
    recentExpenseBars: computeRecentExpenseBars(records),
    timeBuckets: computeTimeBuckets(records, schedules, t)
  };
}

module.exports = {
  buildAnalysis
};

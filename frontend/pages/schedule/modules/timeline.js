const {
  compareDayKeysAsc,
  compareTimelineItemsAsc,
  formatClock,
  formatDate,
  parseDate
} = require("./state");

function weekdayLabel(date, t) {
  const labels = [
    t("page.weekdaySun"),
    t("page.weekdayMon"),
    t("page.weekdayTue"),
    t("page.weekdayWed"),
    t("page.weekdayThu"),
    t("page.weekdayFri"),
    t("page.weekdaySat")
  ];
  return labels[date.getDay()];
}

function formatScheduleRange(item, t) {
  const start = parseDate(item.start_time || item.occur_at);
  if (item.is_all_day) {
    return t("page.fullDay");
  }
  if (!item.end_time) {
    return formatClock(start);
  }
  const end = parseDate(item.end_time, start);
  return `${formatClock(start)} - ${formatClock(end)}`;
}

function normalizeTimelineItem(item, t) {
  const occurDate = parseDate(item.occur_at);
  const isSchedule = item.kind === "schedule";
  const kindLabel = t(
    item.kind === "income"
      ? "page.kindIncome"
      : item.kind === "expense"
        ? "page.kindExpense"
        : "page.kindSchedule"
  );
  const amountText = item.kind === "income" || item.kind === "expense"
    ? `${item.kind === "income" ? "+" : "-"}${item.amount || "0"}`
    : "";
  return {
    ...item,
    idKey: `${item.kind}-${item.source_id}`,
    titleText: isSchedule ? (item.title || t("page.unnamedSchedule")) : (item.category || kindLabel),
    kindLabel,
    creatorName: item.creator_name || t("common.teamMember"),
    locationText: item.location || t("common.unset"),
    noteText: item.note || item.description || t("common.noNote"),
    subtitleText: isSchedule ? formatScheduleRange(item, t) : formatClock(occurDate),
    amountText,
    metaSecondaryText: isSchedule ? "" : (item.category || ""),
    recordSortTime: occurDate.getTime() || 0,
    offsetX: 0,
    leftActionWidth: 0,
    editWidth: 0
  };
}

function normalizeTimelineDay(day, items, t) {
  const date = parseDate(`${day.day_key}T00:00:00`);
  const isToday = day.day_key === formatDate(new Date());
  return {
    ...day,
    is_today: isToday,
    isToday,
    monthText: `${date.getMonth() + 1}`,
    dayText: `${date.getDate()}`,
    weekdayText: weekdayLabel(date, t),
    titleText: isToday ? `${t("page.todayLabel")} - ${day.day_key}` : day.day_key,
    countText: `${items.length}${t("page.countUnit")}`,
    items
  };
}

function buildVisibleDays({ days = [], activeKindFilter = "", t }) {
  return (days || [])
    .slice()
    .sort((left, right) => compareDayKeysAsc(left.day_key, right.day_key))
    .map((day) => {
      const items = (day.items || [])
        .filter((item) => !activeKindFilter || item.kind === activeKindFilter)
        .map((item) => normalizeTimelineItem(item, t))
        .sort(compareTimelineItemsAsc);
      if (!items.length) return null;
      return normalizeTimelineDay(day, items, t);
    })
    .filter(Boolean);
}

function buildDayCountMap(days = []) {
  const map = {};
  (days || []).forEach((day) => {
    map[day.day_key] = Array.isArray(day.items) ? day.items.length : 0;
  });
  return map;
}

function monthStartFromKey(dayKey) {
  const date = parseDate(`${dayKey || formatDate(new Date())}T00:00:00`);
  return new Date(date.getFullYear(), date.getMonth(), 1);
}

function monthTitle(date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}`;
}

function buildCalendarWeeks({ monthKey, anchorDay, days = [] }) {
  const monthStart = monthStartFromKey(monthKey);
  const monthEnd = new Date(monthStart.getFullYear(), monthStart.getMonth() + 1, 0);
  const dayCountMap = buildDayCountMap(days);
  const maxCount = Math.max(1, ...Object.values(dayCountMap), 0);
  const gridStart = new Date(monthStart);
  gridStart.setDate(monthStart.getDate() - monthStart.getDay());
  const gridEnd = new Date(monthEnd);
  gridEnd.setDate(monthEnd.getDate() + (6 - monthEnd.getDay()));

  const weeks = [];
  const todayKey = formatDate(new Date());
  let cursor = new Date(gridStart);
  while (cursor <= gridEnd) {
    const week = [];
    for (let i = 0; i < 7; i += 1) {
      const dayKey = formatDate(cursor);
      const count = dayCountMap[dayKey] || 0;
      const isCurrentMonth = cursor.getMonth() === monthStart.getMonth();
      const intensity = count > 0 ? Math.max(0.12, count / maxCount) : 0;
      week.push({
        dayKey,
        dayText: `${cursor.getDate()}`,
        count,
        isCurrentMonth,
        isToday: dayKey === todayKey,
        isAnchor: dayKey === anchorDay,
        heatStyle: count > 0
          ? `background: rgba(33, 88, 214, ${Math.min(0.2 + intensity * 0.55, 0.85)}); color: #ffffff;`
          : ""
      });
      cursor.setDate(cursor.getDate() + 1);
    }
    weeks.push(week);
  }

  return {
    title: monthTitle(monthStart),
    monthKey: formatDate(monthStart),
    weeks,
    maxCount
  };
}

module.exports = {
  buildCalendarWeeks,
  buildVisibleDays,
  monthStartFromKey
};

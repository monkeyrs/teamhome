const {
  addDays,
  compareDayKeysAsc,
  compareTimelineItemsAsc,
  formatClock,
  formatDate,
  parseDate
} = require("./state");

const SCHEDULE_COLOR_POOL_SIZE = 8;

function startOfDay(date) {
  const next = new Date(date);
  next.setHours(0, 0, 0, 0);
  return next;
}

function dayDiffInclusive(start, end) {
  const diff = startOfDay(end).getTime() - startOfDay(start).getTime();
  return Math.max(Math.floor(diff / (24 * 60 * 60 * 1000)), 0);
}

function buildMultiDayColorMap(days = []) {
  const scheduleMap = new Map();
  (days || []).forEach((day) => {
    (day.items || []).forEach((item) => {
      if (!item || item.kind !== "schedule" || !item.start_time || !item.end_time) return;
      if (scheduleMap.has(`${item.source_id}`)) return;
      const start = parseDate(item.start_time || item.occur_at);
      const end = parseDate(item.end_time, start);
      if (dayDiffInclusive(start, end) <= 0) return;
      scheduleMap.set(`${item.source_id}`, {
        sourceId: `${item.source_id}`,
        startDay: startOfDay(start).getTime(),
        endDay: startOfDay(end).getTime()
      });
    });
  });

  const schedules = Array.from(scheduleMap.values()).sort((left, right) => (
    left.startDay - right.startDay ||
    left.endDay - right.endDay ||
    left.sourceId.localeCompare(right.sourceId)
  ));

  const colorMap = {};
  let active = [];
  schedules.forEach((schedule) => {
    active = active.filter((item) => item.endDay >= schedule.startDay);
    const used = new Set(active.map((item) => item.colorIndex));
    let colorIndex = 0;
    while (colorIndex < SCHEDULE_COLOR_POOL_SIZE && used.has(colorIndex)) {
      colorIndex += 1;
    }
    if (colorIndex >= SCHEDULE_COLOR_POOL_SIZE) {
      colorIndex %= SCHEDULE_COLOR_POOL_SIZE;
    }
    colorMap[schedule.sourceId] = colorIndex;
    active.push({
      endDay: schedule.endDay,
      colorIndex
    });
  });
  return colorMap;
}

function applyMultiDayColors(days = []) {
  const colorMap = buildMultiDayColorMap(days);
  return (days || []).map((day) => ({
    ...day,
    items: (day.items || []).map((item) => ({
      ...item,
      schedule_color_index: colorMap[`${item.source_id}`] ?? 0
    }))
  }));
}

function expandTimelineItems(items = []) {
  const expanded = [];
  (items || []).forEach((item) => {
    if (item.kind !== "schedule" || !item.start_time || !item.end_time) {
      expanded.push(item);
      return;
    }

    const start = parseDate(item.start_time || item.occur_at);
    const end = parseDate(item.end_time, start);
    const spanDays = dayDiffInclusive(start, end);
    if (spanDays <= 0) {
      expanded.push(item);
      return;
    }

    for (let offset = 0; offset <= spanDays; offset += 1) {
      const currentDay = startOfDay(addDays(start, offset));
      const displayDayKey = formatDate(currentDay);
      let segmentRole = "middle";
      if (offset === 0) {
        segmentRole = "start";
      } else if (offset === spanDays) {
        segmentRole = "end";
      }
      expanded.push({
        ...item,
        display_day_key: displayDayKey,
        schedule_segment_role: segmentRole,
        schedule_segment_index: offset,
        schedule_segment_days: spanDays + 1
      });
    }
  });
  return expanded;
}

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
  const segmentRole = isSchedule ? (item.schedule_segment_role || "single") : "single";
  const isMultiDaySchedule = isSchedule && segmentRole !== "single";
  const isMiddleSegment = segmentRole === "middle";
  const scheduleColorIndex = Number.isInteger(item.schedule_color_index) ? item.schedule_color_index : 0;
  const locationText = `${item.location || ""}`.trim();
  const noteText = `${item.note || item.description || ""}`.trim();
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
    idKey: `${item.kind}-${item.source_id}-${item.display_day_key || item.occur_at || "single"}`,
    rowDomId: `timeline-item-${item.kind}-${item.source_id}-${item.display_day_key || "single"}`,
    titleText: isSchedule ? (item.title || t("page.unnamedSchedule")) : (item.category || kindLabel),
    kindLabel,
    segmentRole,
    isMultiDaySchedule,
    isMiddleSegment,
    scheduleColorIndex,
    multiDayCardClass: `timeline-card-with-rail timeline-card-schedule-color-${scheduleColorIndex}`,
    scheduleCardClass: `timeline-card-schedule-color-${scheduleColorIndex}`,
    scheduleLineClass: `schedule-segment-line-color-${scheduleColorIndex}`,
    scheduleNodeClass: `schedule-segment-node-color-${scheduleColorIndex}`,
    scheduleCompactTitleClass: `schedule-compact-title-color-${scheduleColorIndex}`,
    hasSegmentBefore: segmentRole === "middle" || segmentRole === "end",
    hasSegmentAfter: segmentRole === "start" || segmentRole === "middle",
    creatorName: item.creator_name || t("common.teamMember"),
    locationText,
    noteText,
    hasLocation: !!locationText,
    hasNote: !!noteText,
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
  const monthUnit = t("page.monthUnit");
  return {
    ...day,
    is_today: isToday,
    isToday,
    monthText: `${date.getMonth() + 1}${monthUnit === "page.monthUnit" ? "" : monthUnit}`,
    dayText: `${date.getDate()}`,
    weekdayText: weekdayLabel(date, t),
    titleText: isToday ? `${t("page.todayLabel")} - ${day.day_key}` : day.day_key,
    countText: `${items.length}${t("page.countUnit")}`,
    items
  };
}

function buildVisibleDays({ days = [], activeKindFilter = "", t }) {
  const coloredDays = applyMultiDayColors(days);
  const grouped = {};
  (coloredDays || []).forEach((day) => {
    const expandedItems = expandTimelineItems(day.items || []);
    expandedItems.forEach((item) => {
      const dayKey = item.display_day_key || day.day_key;
      if (!grouped[dayKey]) {
        grouped[dayKey] = {
          day_key: dayKey,
          is_today: dayKey === day.day_key ? day.is_today : false,
          items: []
        };
      }
      grouped[dayKey].items.push(item);
    });
  });

  return Object.values(grouped)
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

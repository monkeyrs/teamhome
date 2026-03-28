function pad(value) {
  return `${value}`.padStart(2, "0");
}

function formatDate(date) {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

function formatClock(date) {
  return `${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function addDays(date, days) {
  const next = new Date(date);
  next.setDate(next.getDate() + days);
  return next;
}

function toLocalIso(datePart, timePart, allDay = false) {
  const finalTime = allDay ? "00:00" : (timePart || "00:00");
  return `${datePart}T${finalTime}:00+08:00`;
}

function toWindowStartIso(date) {
  return `${formatDate(date)}T00:00:00+08:00`;
}

function toWindowEndIso(date) {
  return `${formatDate(date)}T23:59:59+08:00`;
}

function parseDate(value, fallback = new Date()) {
  if (!value) return new Date(fallback);
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return new Date(fallback);
  return parsed;
}

function compareDayKeysAsc(leftKey, rightKey) {
  return parseDate(`${leftKey}T00:00:00`).getTime() - parseDate(`${rightKey}T00:00:00`).getTime();
}

function kindSortPriority(kind) {
  return kind === "schedule" ? 0 : 1;
}

function sortLabelForItem(item) {
  const base = item.kind === "schedule"
    ? (item.title || "")
    : (item.category || item.title || "");
  return `${base}`.trim().toLowerCase();
}

function compareTimelineItemsAsc(left, right) {
  const leftTime = parseDate(left.start_time || left.occur_at).getTime();
  const rightTime = parseDate(right.start_time || right.occur_at).getTime();
  if (leftTime !== rightTime) {
    return leftTime - rightTime;
  }

  const kindDiff = kindSortPriority(left.kind) - kindSortPriority(right.kind);
  if (kindDiff !== 0) {
    return kindDiff;
  }

  const labelDiff = sortLabelForItem(left).localeCompare(sortLabelForItem(right));
  if (labelDiff !== 0) {
    return labelDiff;
  }

  return `${left.source_id || ""}`.localeCompare(`${right.source_id || ""}`);
}

function buildEmptyScheduleForm(dateText = formatDate(new Date())) {
  return {
    title: "",
    description: "",
    locationText: "",
    is_all_day: false,
    date: dateText,
    start_clock: "09:00",
    end_date: dateText,
    end_clock: "10:00"
  };
}

function buildEmptyFinanceForm(now = new Date(), type = "expense") {
  return {
    amount: "",
    type,
    occurredDate: formatDate(now),
    occurredTime: formatClock(now),
    category: "",
    locationText: "",
    note: ""
  };
}

function buildCategorySuggestions({ query, presets, commonCategories, limit = 10 }) {
  const trimmed = String(query || "").trim().toLowerCase();
  const merged = [];
  const pool = (presets || []).concat(commonCategories || []);
  pool.forEach((item) => {
    if (!item || merged.includes(item)) return;
    if (!trimmed || item.toLowerCase().includes(trimmed)) {
      merged.push(item);
    }
  });
  return merged.slice(0, limit);
}

module.exports = {
  addDays,
  buildCategorySuggestions,
  buildEmptyFinanceForm,
  buildEmptyScheduleForm,
  compareDayKeysAsc,
  compareTimelineItemsAsc,
  formatClock,
  formatDate,
  parseDate,
  toLocalIso,
  toWindowEndIso,
  toWindowStartIso
};

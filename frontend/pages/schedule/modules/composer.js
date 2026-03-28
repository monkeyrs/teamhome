const {
  addDays,
  formatClock,
  formatDate,
  parseDate,
  toLocalIso
} = require("./state");

function buildScheduleFormFromItem(item) {
  const start = parseDate(item.start_time || item.occur_at);
  const end = item.end_time ? parseDate(item.end_time, start) : start;
  return {
    title: item.title || "",
    description: item.description || "",
    locationText: item.location || "",
    is_all_day: !!item.is_all_day,
    date: formatDate(start),
    start_clock: formatClock(start),
    end_date: formatDate(end),
    end_clock: formatClock(end)
  };
}

function buildScheduleDuplicateForm(item) {
  const originalStart = parseDate(item.start_time || item.occur_at);
  const originalEnd = item.end_time ? parseDate(item.end_time, originalStart) : originalStart;
  const duration = Math.max(originalEnd.getTime() - originalStart.getTime(), 60 * 60 * 1000);
  const nextStart = new Date(originalStart);
  const now = new Date();
  if (nextStart.getTime() <= now.getTime()) {
    const candidate = addDays(now, 1);
    candidate.setHours(originalStart.getHours(), originalStart.getMinutes(), 0, 0);
    nextStart.setTime(candidate.getTime());
  }
  const nextEnd = new Date(nextStart.getTime() + duration);
  return {
    title: item.title || "",
    description: item.description || "",
    locationText: item.location || "",
    is_all_day: !!item.is_all_day,
    date: formatDate(nextStart),
    start_clock: formatClock(nextStart),
    end_date: formatDate(nextEnd),
    end_clock: formatClock(nextEnd)
  };
}

function buildFinanceFormFromItem(item) {
  const occurred = parseDate(item.occur_at || item.created_at);
  const type = item.kind === "income" ? "income" : "expense";
  return {
    amount: item.amount ? `${item.amount}` : "",
    type,
    occurredDate: formatDate(occurred),
    occurredTime: formatClock(occurred),
    category: item.category || "",
    locationText: item.location || "",
    note: item.note || ""
  };
}

function buildSchedulePayload(form) {
  const startTime = toLocalIso(form.date, form.start_clock, form.is_all_day);
  let endTime = toLocalIso(form.end_date || form.date, form.end_clock, form.is_all_day);
  if (new Date(endTime).getTime() < new Date(startTime).getTime()) {
    endTime = startTime;
  }
  return {
    title: form.title,
    description: form.description || null,
    location: form.locationText || null,
    location_latitude: null,
    location_longitude: null,
    is_all_day: !!form.is_all_day,
    start_time: startTime,
    end_time: endTime
  };
}

function buildFinancePayload(form) {
  return {
    amount: Number(form.amount),
    type: form.type,
    occurred_at: toLocalIso(form.occurredDate, form.occurredTime),
    category: form.category,
    location: form.locationText || null,
    location_latitude: null,
    location_longitude: null,
    note: form.note || null
  };
}

module.exports = {
  buildFinanceFormFromItem,
  buildFinancePayload,
  buildScheduleDuplicateForm,
  buildScheduleFormFromItem,
  buildSchedulePayload
};

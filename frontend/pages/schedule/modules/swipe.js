function cloneVisibleDays(visibleDays = []) {
  return (visibleDays || []).map((day) => ({
    ...day,
    items: (day.items || []).map((item) => ({ ...item }))
  }));
}

function resetSwipeItem(item) {
  item.offsetX = 0;
  item.leftActionWidth = 0;
  item.editWidth = 0;
}

function closeSwipeRows(visibleDays = []) {
  const next = cloneVisibleDays(visibleDays);
  next.forEach((day) => {
    day.items.forEach((item) => resetSwipeItem(item));
  });
  return next;
}

function buildSwipeMoveState({ visibleDays = [], dayIndex, itemIndex, deltaX, laziness, maxSwipe }) {
  const next = cloneVisibleDays(visibleDays);
  next.forEach((day, dayCursor) => {
    day.items.forEach((item, itemCursor) => {
      if (dayCursor !== dayIndex || itemCursor !== itemIndex) {
        resetSwipeItem(item);
      }
    });
  });

  const current = next[dayIndex] && next[dayIndex].items[itemIndex];
  if (!current) {
    return next;
  }

  const horizontalDistance = Math.abs(deltaX);
  if (horizontalDistance <= laziness) {
    resetSwipeItem(current);
    return next;
  }

  if (deltaX < 0) {
    const offsetX = Math.max(deltaX + laziness, -maxSwipe);
    current.offsetX = offsetX;
    current.leftActionWidth = Math.min(Math.abs(offsetX), maxSwipe);
    current.editWidth = 0;
    return next;
  }

  const offsetX = Math.min(deltaX - laziness, maxSwipe);
  current.offsetX = offsetX;
  current.editWidth = Math.min(offsetX, maxSwipe);
  current.leftActionWidth = 0;
  return next;
}

function resolveSwipeEnd({
  visibleDays = [],
  dayIndex,
  itemIndex,
  swipeDirection,
  hardActionThreshold,
  copyButtonWidth,
  editButtonWidth
}) {
  const next = cloneVisibleDays(visibleDays);
  const current = next[dayIndex] && next[dayIndex].items[itemIndex];
  if (!current) {
    return { action: "", visibleDays: next };
  }

  if (swipeDirection !== "horizontal") {
    resetSwipeItem(current);
    return { action: "", visibleDays: next };
  }

  if (current.offsetX <= -hardActionThreshold) {
    return { action: "duplicate", visibleDays: closeSwipeRows(next) };
  }

  if (current.offsetX >= hardActionThreshold) {
    return { action: "edit", visibleDays: closeSwipeRows(next) };
  }

  if (current.offsetX < 0) {
    const shouldOpenCopy = Math.abs(current.offsetX) >= copyButtonWidth / 2;
    current.offsetX = shouldOpenCopy ? -copyButtonWidth : 0;
    current.leftActionWidth = shouldOpenCopy ? copyButtonWidth : 0;
    current.editWidth = 0;
    return { action: "", visibleDays: next };
  }

  const shouldOpenEdit = current.offsetX >= editButtonWidth / 2;
  current.offsetX = shouldOpenEdit ? editButtonWidth : 0;
  current.editWidth = shouldOpenEdit ? editButtonWidth : 0;
  current.leftActionWidth = 0;
  return { action: "", visibleDays: next };
}

module.exports = {
  buildSwipeMoveState,
  cloneVisibleDays,
  closeSwipeRows,
  resolveSwipeEnd
};

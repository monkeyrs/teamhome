const {
  buildFinanceFormFromItem,
  buildScheduleDuplicateForm,
  buildScheduleFormFromItem
} = require("./composer");
const {
  buildEmptyFinanceForm,
  buildEmptyScheduleForm,
  formatDate
} = require("./state");

function buildScheduleCreateComposerState(dateText = formatDate(new Date())) {
  return {
    isQuickCreateOpen: false,
    isFilterOpen: false,
    composerOpen: true,
    composerKind: "schedule",
    composerMode: "create",
    editingId: "",
    scheduleForm: buildEmptyScheduleForm(dateText)
  };
}

function buildFinanceCreateComposerState({ type, categorySuggestions, now = new Date() }) {
  return {
    isQuickCreateOpen: false,
    isFilterOpen: false,
    composerOpen: true,
    composerKind: "finance",
    composerMode: "create",
    editingId: "",
    financeForm: buildEmptyFinanceForm(now, type),
    categorySuggestions
  };
}

function buildScheduleEditComposerState(item) {
  return {
    isQuickCreateOpen: false,
    isFilterOpen: false,
    composerOpen: true,
    composerKind: "schedule",
    composerMode: "edit",
    editingId: item.source_id,
    scheduleForm: buildScheduleFormFromItem(item)
  };
}

function buildScheduleDuplicateComposerState(item) {
  return {
    isQuickCreateOpen: false,
    isFilterOpen: false,
    composerOpen: true,
    composerKind: "schedule",
    composerMode: "create",
    editingId: "",
    scheduleForm: buildScheduleDuplicateForm(item)
  };
}

function buildFinanceEditComposerState(item, categorySuggestions) {
  return {
    isQuickCreateOpen: false,
    isFilterOpen: false,
    composerOpen: true,
    composerKind: "finance",
    composerMode: "edit",
    editingId: item.source_id,
    financeForm: buildFinanceFormFromItem(item),
    categorySuggestions
  };
}

function buildFinanceDuplicateComposerState(item, categorySuggestions) {
  return {
    isQuickCreateOpen: false,
    isFilterOpen: false,
    composerOpen: true,
    composerKind: "finance",
    composerMode: "create",
    editingId: "",
    financeForm: buildFinanceFormFromItem(item),
    categorySuggestions
  };
}

function buildComposerClosedState(now = new Date()) {
  return {
    composerOpen: false,
    composerKind: "schedule",
    composerMode: "create",
    editingId: "",
    scheduleForm: buildEmptyScheduleForm(formatDate(now)),
    financeForm: buildEmptyFinanceForm(now),
    categorySuggestions: [],
    placeSuggestions: []
  };
}

module.exports = {
  buildComposerClosedState,
  buildFinanceCreateComposerState,
  buildFinanceDuplicateComposerState,
  buildFinanceEditComposerState,
  buildScheduleCreateComposerState,
  buildScheduleDuplicateComposerState,
  buildScheduleEditComposerState
};

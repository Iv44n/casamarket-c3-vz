// Shared sizing so every chart on /atenciones reads as one consistent
// system instead of each picking its own numbers. Values restored to match
// what the charts looked like before this file existed (agent/campaign tick
// + bar labels were 12px, donut center was 22px).
export const CHART_AXIS_LABEL_FONT_SIZE = 12
export const CHART_VALUE_LABEL_FONT_SIZE = 12
// The donut's arc label was one size up from the bar charts' labels in the
// original commit (13 vs 12) -- kept distinct rather than merged into
// CHART_VALUE_LABEL_FONT_SIZE so restoring sizes stays exact.
export const CHART_ARC_LABEL_FONT_SIZE = 13
export const CHART_LEGEND_FONT_SIZE = 12
// The one "hero" number per card (donut center value, hierarchy level total).
export const CHART_BIG_NUMBER_FONT_SIZE = 22
// Row pitch for horizontal bar charts (agent/campaign) -- modest, matching
// the original scale rather than the oversized/undersized experiments.
export const CHART_ROW_HEIGHT_PX = 36
export const CHART_MIN_HEIGHT_PX = 220

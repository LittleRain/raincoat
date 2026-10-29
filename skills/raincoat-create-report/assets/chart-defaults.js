/**
 * chart-defaults.js — Standardized Chart.js configuration
 *
 * Provides unified chart styling that matches base-report.css design tokens.
 * Inline this file AFTER Chart.js in the report HTML.
 *
 * Exports (on window):
 *   REPORT_PALETTE  — 10-color array for multi-series charts
 *   REPORT_FORMAT   — value formatters { gmv, pv, pct, num, auto }
 *   REPORT_WOW      — WoW change calculator
 *   reportChart     — chart factory: reportChart(canvasId, config) → Chart
 *   chartPresets    — preset configs: { line, bar, doughnut, combo }
 */

(function () {
  'use strict';

  /* ── Design tokens (must match base-report.css :root) ── */
  var COLORS = {
    ink:    '#f7f8f8',
    text2:  '#d0d6e0',
    text3:  '#8a8f98',
    text4:  '#62666d',
    card:   '#191a1b',
    border: 'rgba(255,255,255,0.08)',
    grid:   'rgba(255,255,255,0.06)',
    accent: '#5e6ad2',
    up:     '#10b981',
    down:   '#f87171',
    warn:   '#fbbf24'
  };

  var PALETTE = [
    '#5e6ad2', '#10b981', '#fbbf24', '#a78bfa', '#f472b6',
    '#22d3ee', '#f87171', '#6366f1', '#fb923c', '#14b8a6'
  ];

  var FONT = '"PingFang SC", "Noto Sans SC", -apple-system, sans-serif';

  /* ── Apply Chart.js global defaults ── */
  Chart.defaults.color = COLORS.text3;
  Chart.defaults.borderColor = COLORS.grid;
  Chart.defaults.font.family = FONT;
  Chart.defaults.font.size = 11;
  Chart.defaults.plugins.legend.labels.usePointStyle = true;
  Chart.defaults.plugins.legend.labels.padding = 12;
  Chart.defaults.plugins.legend.labels.font = { size: 11 };
  Chart.defaults.plugins.tooltip.backgroundColor = COLORS.card;
  Chart.defaults.plugins.tooltip.borderColor = COLORS.border;
  Chart.defaults.plugins.tooltip.borderWidth = 1;
  Chart.defaults.plugins.tooltip.titleFont = { size: 12, weight: 600 };
  Chart.defaults.plugins.tooltip.bodyFont = { size: 11 };
  Chart.defaults.plugins.tooltip.padding = 10;
  Chart.defaults.plugins.tooltip.cornerRadius = 8;
  Chart.defaults.plugins.tooltip.displayColors = true;
  Chart.defaults.plugins.tooltip.boxPadding = 4;
  Chart.defaults.elements.line.tension = 0.3;
  Chart.defaults.elements.line.borderWidth = 2;
  Chart.defaults.elements.bar.borderRadius = 4;
  Chart.defaults.responsive = true;
  Chart.defaults.maintainAspectRatio = false;
  Chart.defaults.scales.linear.beginAtZero = true;  // all Y axes start from 0

  // Register datalabels plugin if available
  if (typeof ChartDataLabels !== 'undefined') {
    Chart.register(ChartDataLabels);
    Chart.defaults.plugins.datalabels = { display: false };
  }


  /* ── Value formatters ── */
  var FORMAT = {
    /**
     * Format GMV values: ¥1.2万, ¥3,456
     */
    gmv: function (v) {
      if (v == null || isNaN(v)) return '-';
      if (v >= 1e8) return '\u00a5' + (v / 1e8).toFixed(2) + '\u4ebf';
      if (v >= 1e4) return '\u00a5' + (v / 1e4).toFixed(1) + '\u4e07';
      if (v >= 1000) return '\u00a5' + Math.round(v).toLocaleString();
      return '\u00a5' + v.toFixed(0);
    },

    /**
     * Format PV/traffic values: 1.2亿, 3.4万
     */
    pv: function (v) {
      if (v == null || isNaN(v)) return '-';
      if (v >= 1e8) return (v / 1e8).toFixed(2) + '\u4ebf';
      if (v >= 1e4) return (v / 1e4).toFixed(1) + '\u4e07';
      return v.toLocaleString();
    },

    /**
     * Format percentage values: 12.34%
     * Auto-detects decimal-form ratios (e.g. 0.0475 → 4.75%)
     * Values < 1 are assumed to be raw ratios and multiplied by 100.
     * Values >= 1 are assumed to already be in percentage form.
     */
    pct: function (v) {
      if (v == null || isNaN(v)) return '-';
      // Auto-convert decimal ratios: 0.0475 → 4.75, 0.85 → 85.0
      if (Math.abs(v) < 1) v = v * 100;
      return v.toFixed(2) + '%';
    },

    /**
     * Format count values: 3.4万
     */
    num: function (v) {
      if (v == null || isNaN(v)) return '-';
      if (v >= 1e4) return (v / 1e4).toFixed(1) + '\u4e07';
      return v.toLocaleString();
    },

    /**
     * Auto-detect format by metric name (Chinese or English).
     * 率值 → pct, 金额 → gmv, 人数 → num, 量级 → pv
     */
    auto: function (metricName, v) {
      if (v == null || isNaN(v)) return '-';
      var n = String(metricName);
      // Rate / ratio metrics → percentage (GPM is per-mille GMV, not a ratio)
      if (/率|CTR|占比|比例|比率|cvr|conversion/i.test(n)) return FORMAT.pct(v);
      // Money metrics → ¥ prefixed (includes GPM = GMV per 1000 impressions)
      if (/GMV|GPM|客单价|金额|收入|营收|revenue|arpu|price/i.test(n)) return FORMAT.gmv(v);
      // People metrics → plain number
      if (/DAU|MAU|买家|用户|新客|商家|seller|buyer|user/i.test(n)) return FORMAT.num(v);
      // Volume metrics → large number
      if (/PV|UV|曝光|点击|订单|次数|impression|click|order|exposure/i.test(n)) return FORMAT.pv(v);
      // Fallback
      return FORMAT.num(v);
    }
  };


  /* ── WoW change calculator ── */
  function calcWoW(current, previous) {
    if (!previous || previous === 0) return { text: '-', cls: '' };
    var pct = (current - previous) / previous * 100;
    return {
      text: (pct > 0 ? '+' : '') + pct.toFixed(1) + '%',
      cls: pct > 0 ? 'up' : (pct < 0 ? 'down' : 'neutral'),
      value: pct
    };
  }


  /* ── Chart factory ── */
  function reportChart(canvasId, config) {
    var el = document.getElementById(canvasId);
    if (!el) {
      console.warn('[report-chart] Canvas not found: ' + canvasId);
      return null;
    }
    return new Chart(el, config);
  }


  /* ── Preset configurations ── */
  var PRESETS = {
    /**
     * Line chart preset
     * Usage: reportChart('id', chartPresets.line(labels, datasets, opts))
     */
    line: function (labels, datasets, opts) {
      opts = opts || {};
      return {
        type: 'line',
        data: {
          labels: labels,
          datasets: datasets.map(function (ds, i) {
            return Object.assign({
              borderColor: PALETTE[i % PALETTE.length],
              backgroundColor: 'transparent',
              pointRadius: 3,
              pointHoverRadius: 5,
              tension: 0.3,
              borderWidth: 2
            }, ds);
          })
        },
        options: Object.assign({
          responsive: true,
          maintainAspectRatio: false,
          scales: {
            y: {
              ticks: {
                callback: opts.yFormat ? function (v) { return FORMAT[opts.yFormat](v); } : undefined
              }
            }
          },
          plugins: {
            datalabels: { display: false }
          }
        }, opts.chartOptions || {})
      };
    },

    /**
     * Bar chart preset
     */
    bar: function (labels, datasets, opts) {
      opts = opts || {};
      return {
        type: 'bar',
        data: {
          labels: labels,
          datasets: datasets.map(function (ds, i) {
            return Object.assign({
              backgroundColor: PALETTE[i % PALETTE.length] + 'B3', // 70% opacity
              borderRadius: 4,
              maxBarThickness: 48
            }, ds);
          })
        },
        options: Object.assign({
          responsive: true,
          maintainAspectRatio: false,
          scales: {
            x: { stacked: !!opts.stacked },
            y: {
              stacked: !!opts.stacked,
              ticks: {
                callback: opts.yFormat ? function (v) { return FORMAT[opts.yFormat](v); } : undefined
              }
            }
          }
        }, opts.chartOptions || {})
      };
    },

    /**
     * Doughnut chart preset
     */
    doughnut: function (labels, data, opts) {
      opts = opts || {};
      return {
        type: 'doughnut',
        data: {
          labels: labels,
          datasets: [{
            data: data,
            backgroundColor: PALETTE.slice(0, labels.length),
            borderWidth: 0
          }]
        },
        options: Object.assign({
          responsive: true,
          maintainAspectRatio: false,
          cutout: '55%',
          plugins: {
            legend: {
              position: 'bottom',
              labels: { padding: 10, usePointStyle: true, font: { size: 11 } }
            }
          }
        }, opts.chartOptions || {})
      };
    },

    /**
     * Combo chart preset (bar + line, dual Y axis)
     *
     * Styling rules:
     *   - Left axis (y):  bars, for absolute values (GMV, PV, orders)
     *   - Right axis (y1): lines, for ratios/percentages (占比%, 转化率)
     *   - Bars use 70% opacity fill, no border
     *   - Lines use solid 2px stroke, 4px dot, contrasting color from bars
     *   - Right axis grid lines hidden (drawOnChartArea: false)
     *   - Right axis label includes % suffix by default
     *   - Line datasets MUST set { type: 'line', yAxisID: 'y1' }
     *
     * Usage:
     *   reportChart('c1', chartPresets.combo(labels, [
     *     { label: '小店PV', data: [...], yAxisID: 'y' },
     *     { label: '自营PV', data: [...], yAxisID: 'y' },
     *     { type: 'line', label: '小店占比%', data: [...], yAxisID: 'y1' }
     *   ], { yFormat: 'pv', y1Format: 'pct' }));
     */
    combo: function (labels, datasets, opts) {
      opts = opts || {};
      // Separate bar and line datasets for smart color assignment
      var barIdx = 0, lineIdx = 0;
      // Line colors: pick from end of palette to contrast with bar colors
      var lineColors = ['#fbbf24', '#f472b6', '#22d3ee', '#14b8a6'];
      return {
        type: 'bar',
        data: {
          labels: labels,
          datasets: datasets.map(function (ds) {
            var isLine = ds.type === 'line';
            if (isLine) {
              var lc = lineColors[lineIdx % lineColors.length];
              lineIdx++;
              return Object.assign({
                type: 'line',
                backgroundColor: 'transparent',
                borderColor: lc,
                borderWidth: 2,
                tension: 0.3,
                pointRadius: 4,
                pointHoverRadius: 6,
                pointBackgroundColor: lc,
                pointBorderColor: COLORS.card,
                pointBorderWidth: 2,
                yAxisID: 'y1',
                order: 0  // lines render on top
              }, ds);
            } else {
              var bc = PALETTE[barIdx % PALETTE.length];
              barIdx++;
              return Object.assign({
                backgroundColor: bc + 'B3',
                borderRadius: 4,
                borderWidth: 0,
                maxBarThickness: 48,
                yAxisID: 'y',
                order: 1  // bars render behind
              }, ds);
            }
          })
        },
        options: Object.assign({
          responsive: true,
          maintainAspectRatio: false,
          interaction: {
            mode: 'index',
            intersect: false
          },
          scales: {
            y: {
              position: 'left',
              beginAtZero: true,
              grid: { color: COLORS.grid },
              ticks: {
                color: COLORS.text3,
                callback: opts.yFormat ? function (v) { return FORMAT[opts.yFormat](v); } : undefined
              }
            },
            y1: {
              position: 'right',
              beginAtZero: true,
              grid: { drawOnChartArea: false },
              ticks: {
                color: COLORS.text4,
                callback: opts.y1Format ? function (v) { return FORMAT[opts.y1Format](v); } : function (v) { return v + '%'; }
              }
            }
          },
          plugins: {
            datalabels: { display: false },
            legend: {
              labels: {
                usePointStyle: true,
                padding: 12,
                font: { size: 11 }
              }
            },
            tooltip: {
              callbacks: {
                label: function (ctx) {
                  var ds = ctx.dataset;
                  var fmt = ds.yAxisID === 'y1'
                    ? (opts.y1Format ? FORMAT[opts.y1Format] : FORMAT.pct)
                    : (opts.yFormat  ? FORMAT[opts.yFormat]  : FORMAT.num);
                  return ds.label + ': ' + fmt(ctx.parsed.y);
                }
              }
            }
          }
        }, opts.chartOptions || {})
      };
    }
  };


  /* ── HTML helpers for metric cards & table cells ── */
  var HTML = {
    /**
     * Metric card HTML
     * metricCard('GMV', '¥12.3万', { text: '+5.2%', cls: 'up' }, 'green')
     */
    metricCard: function (label, value, wow, color) {
      var cls = color ? ' ' + color : '';
      var h = '<div class="metric-card' + cls + '">';
      h += '<p class="metric-label">' + label + '</p>';
      h += '<p class="metric-value">' + value + '</p>';
      if (wow && wow.text && wow.text !== '-') {
        h += '<p class="metric-sub"><span class="delta ' + wow.cls + '">' + wow.text + '</span></p>';
      }
      return h + '</div>';
    },

    /**
     * WoW tag for table cells
     * wowTag({ text: '+5.2%', cls: 'up' })
     */
    wowTag: function (wow) {
      if (!wow || !wow.cls) return '<span class="tag">-</span>';
      return '<span class="tag tag-' + wow.cls + '">' + wow.text + '</span>';
    }
  };


  /* ── Expose on window ── */
  window.REPORT_PALETTE  = PALETTE;
  window.REPORT_COLORS   = COLORS;
  window.REPORT_FORMAT   = FORMAT;
  window.REPORT_WOW      = calcWoW;
  window.reportChart     = reportChart;
  window.chartPresets    = PRESETS;
  window.reportHTML      = HTML;

})();

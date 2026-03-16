/* source-lightbox SPA — vanilla JS, fully offline (no fetch needed) */
(function () {
  "use strict";

  const M = window.MANIFEST;
  const PAGE_SIZE = 50;

  /* ── Acronym map for display formatting ── */
  const ACRONYMS = {
    "psd": "PSD", "pac": "PAC", "mvpa": "MVPA", "roi": "ROI", "lmm": "LMM",
    "itc": "ITC", "ersp": "ERSP", "stp": "STP", "svm": "SVM", "nbs": "NBS",
    "assr": "ASSR", "qc": "QC", "eeg": "EEG", "ica": "ICA", "falff": "fALFF",
    "fdr": "FDR", "aic": "AIC", "bic": "BIC", "se": "SE", "df": "df",
  };

  /* ── Group label map for readable contrast display ── */
  const GROUP_LABELS = {
    "vehicle": "Vehicle",
    "6mgkg": "AUT00201 (6 mg/kg)",
    "30mgkg": "AUT00206 (30 mg/kg)",
  };

  /* ── State ── */
  let currentSource = null;
  let lightbox = null;

  /* ── Init ── */
  document.addEventListener("DOMContentLoaded", function () {
    document.getElementById("gallery-title").textContent = M.title || "Gallery";
    document.title = M.title || "Source Analysis Gallery";
    buildSidebar();
    initThemeToggle();
    initSearch();
    initKeyboard();
    window.addEventListener("hashchange", route);
    route();
  });

  /* ── Router ── */
  function route() {
    var hash = location.hash.slice(1) || "/overview";
    var parts = hash.split("/").filter(Boolean);
    highlightNav(hash);

    if (parts[0] === "overview" || parts.length === 0) {
      renderOverview();
    } else if (parts[0] === "search") {
      renderSearch(decodeURIComponent(parts.slice(1).join("/")));
    } else if (parts[0] === "localization") {
      if (parts[1] === "qc") renderQC(parts[2]);
      else if (parts[1] === "subjects") renderSubjects(parts[2]);
      else renderLocalizationHome();
    } else if (parts[0] === "analytics") {
      // #/analytics/<source>/<paradigm>/<analysis>
      var src = decodeURIComponent(parts[1] || "");
      if (parts.length >= 4) {
        renderAnalysis(parts[2], parts[3], src);
      } else if (parts.length === 3) {
        renderStudyDesign(parts[2], src);
      } else {
        renderSourceHome(src);
      }
    } else {
      renderOverview();
    }
  }

  /* ── Sidebar ── */
  function buildSidebar() {
    var nav = document.getElementById("sidebar-nav");
    var html = "";

    // Overview
    html += '<a class="nav-item" href="#/overview" data-route="/overview">Overview</a>';

    // Localization
    if (Object.keys(M.localization).length > 0) {
      html += '<div class="nav-divider"></div>';
      html += '<div class="nav-section-title">Localization</div>';
      for (var source of Object.keys(M.localization)) {
        html += navItem("/localization/qc/" + source, "QC: " + source);
        html += navItem("/localization/subjects/" + source, "Subjects: " + source);
      }
    }

    // Analytics — grouped by source, then study design (paradigm), then analysis
    if (M.sources.length > 0) {
      html += '<div class="nav-divider"></div>';
      html += '<div class="nav-section-title">Analytics</div>';

      for (var si = 0; si < M.sources.length; si++) {
        var src = M.sources[si];
        // Only show source header if multiple sources
        if (M.sources.length > 1) {
          html += '<div class="nav-paradigm">' + escapeHtml(src) + '</div>';
        }
        // Group paradigms that have data for this source
        for (var paradigm of Object.keys(M.paradigms)) {
          var analyses = M.paradigms[paradigm];
          var hasData = false;
          for (var aname of Object.keys(analyses)) {
            var adata = analyses[aname];
            if ((adata.figures[src] && adata.figures[src].length > 0) ||
                (adata.tables[src] && adata.tables[src].length > 0)) {
              hasData = true;
              break;
            }
          }
          if (!hasData) continue;

          var srcEnc = encodeURIComponent(src);
          html += '<div class="nav-study-design">' + formatName(paradigm) + '</div>';
          for (var analysis of Object.keys(analyses)) {
            var ad = analyses[analysis];
            if ((ad.figures[src] && ad.figures[src].length > 0) ||
                (ad.tables[src] && ad.tables[src].length > 0) ||
                ad.summary) {
              var r = "/analytics/" + srcEnc + "/" + paradigm + "/" + analysis;
              html += navItem(r, formatName(analysis));
            }
          }
        }
      }
    }

    nav.innerHTML = html;
  }

  function navItem(route, label) {
    return '<a class="nav-item" href="#' + route + '" data-route="' + route + '">' + label + '</a>';
  }

  function highlightNav(hash) {
    document.querySelectorAll(".nav-item").forEach(function (el) {
      el.classList.toggle("active", el.getAttribute("data-route") === hash.replace("#", ""));
    });
  }

  /* ── Overview ── */
  function renderOverview() {
    setBreadcrumb(["Overview"]);
    clearSourceSelector();
    var s = M.stats;
    var html = '<h2 class="section-header">Overview</h2>';
    html += '<div class="overview-grid">';
    html += statCard(s.total_figures, "Figures");
    html += statCard(s.total_tables, "Tables");
    html += statCard(s.total_summaries, "Summaries");
    html += statCard(s.paradigm_count, "Study Designs");
    html += statCard(M.sources.length, "Sources");
    html += "</div>";

    // List by source → paradigm → analysis
    for (var si = 0; si < M.sources.length; si++) {
      var src = M.sources[si];
      var srcEnc = encodeURIComponent(src);
      if (M.sources.length > 1) {
        html += '<h2 class="section-header">' + escapeHtml(src) + '</h2>';
      }
      for (var paradigm of Object.keys(M.paradigms)) {
        var analyses = M.paradigms[paradigm];
        var items = [];
        for (var aname of Object.keys(analyses)) {
          var ad = analyses[aname];
          var nf = (ad.figures[src] || []).length;
          var nt = (ad.tables[src] || []).length;
          if (nf > 0 || nt > 0 || ad.summary) {
            items.push({ name: aname, nf: nf, nt: nt });
          }
        }
        if (items.length === 0) continue;
        html += '<h3 style="margin:12px 0 6px">' + formatName(paradigm) + '</h3>';
        html += "<ul>";
        for (var item of items) {
          html += '<li><a href="#/analytics/' + srcEnc + '/' + paradigm + '/' + item.name + '">' +
            formatName(item.name) + '</a> — ' + item.nf + ' figures, ' + item.nt + ' tables</li>';
        }
        html += "</ul>";
      }
    }

    setContent(html);
  }

  function statCard(value, label) {
    return '<div class="stat-card"><div class="stat-value">' + value + '</div><div class="stat-label">' + label + '</div></div>';
  }

  /* ── Source Home (list paradigms for a source) ── */
  function renderSourceHome(src) {
    setBreadcrumb(["Analytics", src]);
    clearSourceSelector();
    var srcEnc = encodeURIComponent(src);
    var html = '<h2 class="section-header">' + escapeHtml(src) + '</h2>';

    for (var paradigm of Object.keys(M.paradigms)) {
      var analyses = M.paradigms[paradigm];
      var items = [];
      for (var aname of Object.keys(analyses)) {
        var ad = analyses[aname];
        if ((ad.figures[src] && ad.figures[src].length > 0) ||
            (ad.tables[src] && ad.tables[src].length > 0) || ad.summary) {
          items.push(aname);
        }
      }
      if (items.length === 0) continue;
      html += '<h3 style="margin:12px 0 6px">' + formatName(paradigm) + '</h3>';
      html += "<ul>";
      for (var a of items) {
        html += '<li><a href="#/analytics/' + srcEnc + '/' + paradigm + '/' + a + '">' + formatName(a) + '</a></li>';
      }
      html += "</ul>";
    }
    setContent(html);
  }

  /* ── Study Design page (list analyses for a paradigm+source) ── */
  function renderStudyDesign(paradigm, src) {
    var analyses = M.paradigms[paradigm];
    if (!analyses) {
      setContent('<div class="empty-state"><p>Study design not found</p></div>');
      return;
    }
    setBreadcrumb(["Analytics", src, formatName(paradigm)]);
    clearSourceSelector();
    var srcEnc = encodeURIComponent(src);

    var html = '<h2 class="section-header">' + formatName(paradigm) + '</h2>';
    html += "<ul>";
    for (var aname of Object.keys(analyses)) {
      var ad = analyses[aname];
      var nf = (ad.figures[src] || []).length;
      var nt = (ad.tables[src] || []).length;
      if (nf > 0 || nt > 0 || ad.summary) {
        html += '<li><a href="#/analytics/' + srcEnc + '/' + paradigm + '/' + aname + '">' +
          formatName(aname) + '</a> — ' + nf + ' figures, ' + nt + ' tables</li>';
      }
    }
    html += "</ul>";
    setContent(html);
  }

  /* ── Analysis Page ── */
  function renderAnalysis(paradigm, analysis, src) {
    var data = (M.paradigms[paradigm] || {})[analysis];
    if (!data) {
      setContent('<div class="empty-state"><p>Analysis not found</p></div>');
      return;
    }

    setBreadcrumb(["Analytics", src, formatName(paradigm), formatName(analysis)]);

    // Source selector (if multiple sources have this analysis)
    var sources = M.sources.filter(function (s) {
      return (data.figures[s] && data.figures[s].length > 0) ||
             (data.tables[s] && data.tables[s].length > 0);
    });

    if (sources.length > 1) {
      renderSourceSelector(sources, src, function (newSrc) {
        location.hash = "#/analytics/" + encodeURIComponent(newSrc) + "/" + paradigm + "/" + analysis;
      });
    } else {
      clearSourceSelector();
    }

    renderAnalysisContent(paradigm, analysis, data, src, sources);
  }

  function renderAnalysisContent(paradigm, analysis, data, source, allSources) {
    var html = '<h2 class="section-header">' + formatName(paradigm) + ' — ' + formatName(analysis) + '</h2>';

    // Summary — at the top
    if (data.summary) {
      html += '<div class="summary-content">' + data.summary + '</div>';
    }

    // Comparison mode
    var sourcesWithFigs = allSources.filter(function (s) { return data.figures[s] && data.figures[s].length > 0; });

    if (sourcesWithFigs.length > 1 && source === "__compare__") {
      html += renderComparisonGrid(data, sourcesWithFigs);
    } else {
      // Figures
      var figs = (data.figures[source] || []);
      if (figs.length > 0) {
        html += '<h3 class="section-header" style="font-size:15px">Figures</h3>';
        html += renderFigureGrid(figs, PAGE_SIZE);
      }
    }

    // Tables
    var tableSource = data.tables[source] ? source : Object.keys(data.tables)[0];
    var tables = data.tables[tableSource] || [];
    if (tables.length > 0) {
      html += '<h3 class="section-header" style="font-size:15px">Tables</h3>';
      html += '<div class="tables-section">';
      for (var ti = 0; ti < tables.length; ti++) {
        var tbl = tables[ti];
        var id = "tbl-" + ti + "-" + tbl.filename.replace(/[^a-z0-9]/gi, "_");
        var displayName = formatTableFilename(tbl.filename);
        html += '<button class="table-toggle" data-table-idx="' + ti + '" data-table-id="' + id + '">';
        html += '<span class="arrow">&#9654;</span> ' + displayName;
        html += "</button>";
        html += '<div id="' + id + '" class="table-container" style="display:none"></div>';
      }
      html += "</div>";
    }

    setContent(html);
    initLightbox();
    bindTableToggles(tables);
  }

  /* ── Localization Pages ── */
  function renderLocalizationHome() {
    setBreadcrumb(["Localization"]);
    clearSourceSelector();
    var html = '<h2 class="section-header">Localization</h2>';
    for (var source of Object.keys(M.localization)) {
      html += '<h3 style="margin:12px 0">' + escapeHtml(source) + '</h3>';
      html += '<p><a href="#/localization/qc/' + encodeURIComponent(source) + '">QC Dashboard</a></p>';
      html += '<p><a href="#/localization/subjects/' + encodeURIComponent(source) + '">Per-Subject Figures</a></p>';
    }
    setContent(html);
  }

  function renderQC(sourceEnc) {
    var source = decodeURIComponent(sourceEnc || "");
    var loc = M.localization[source];
    if (!loc) { setContent('<div class="empty-state">Source not found</div>'); return; }

    setBreadcrumb(["Localization", "QC", source]);
    clearSourceSelector();

    var html = '<h2 class="section-header">QC — ' + escapeHtml(source) + '</h2>';

    if (loc.qc_metrics && loc.qc_metrics.length > 0) {
      html += '<h3 class="section-header" style="font-size:15px">QC Metrics</h3>';
      html += renderQCMetricsTable(loc.qc_metrics);
    }

    if (loc.qc_figures && loc.qc_figures.length > 0) {
      html += '<h3 class="section-header" style="font-size:15px">QC Figures</h3>';
      html += renderFigureGrid(loc.qc_figures, PAGE_SIZE);
    }

    if (loc.qc_report) {
      html += '<h3 class="section-header" style="font-size:15px">QC Report</h3>';
      html += '<iframe class="qc-iframe" src="' + loc.qc_report + '"></iframe>';
    }

    setContent(html);
    initLightbox();
    initTableSort();
  }

  function renderQCMetricsTable(metrics) {
    if (!metrics || metrics.length === 0) return "";
    var headers = Object.keys(metrics[0]);
    var html = '<div class="table-container"><table><thead><tr>';
    for (var h of headers) {
      html += '<th>' + escapeHtml(h) + '<span class="sort-indicator"></span></th>';
    }
    html += "</tr></thead><tbody>";
    for (var row of metrics) {
      html += "<tr>";
      for (var h of headers) {
        html += '<td>' + escapeHtml(row[h] || "") + '</td>';
      }
      html += "</tr>";
    }
    html += "</tbody></table></div>";
    return html;
  }

  function renderSubjects(sourceEnc) {
    var source = decodeURIComponent(sourceEnc || "");
    var loc = M.localization[source];
    if (!loc) { setContent('<div class="empty-state">Source not found</div>'); return; }

    setBreadcrumb(["Localization", "Subjects", source]);
    clearSourceSelector();

    var subjects = Object.keys(loc.subjects).sort();
    if (subjects.length === 0) {
      setContent('<div class="empty-state"><p>No subject figures found</p></div>');
      return;
    }

    var html = '<h2 class="section-header">Subjects — ' + escapeHtml(source) + '</h2>';
    html += '<div class="subject-selector"><label>Subject: <select id="subject-select">';
    for (var sub of subjects) {
      html += '<option value="' + sub + '">' + sub + '</option>';
    }
    html += "</select></label></div>";
    html += '<div id="subject-figures"></div>';

    setContent(html);

    var sel = document.getElementById("subject-select");
    sel.addEventListener("change", function () {
      renderSubjectFigures(loc.subjects[sel.value]);
    });
    renderSubjectFigures(loc.subjects[subjects[0]]);
  }

  function renderSubjectFigures(figs) {
    var container = document.getElementById("subject-figures");
    container.innerHTML = renderFigureGrid(figs || [], 100);
    initLightbox();
  }

  /* ── Search ── */
  function initSearch() {
    var input = document.getElementById("search-input");
    var debounce = null;
    input.addEventListener("input", function () {
      clearTimeout(debounce);
      debounce = setTimeout(function () {
        var q = input.value.trim();
        if (q.length >= 2) {
          location.hash = "#/search/" + encodeURIComponent(q);
        } else if (q.length === 0) {
          location.hash = "#/overview";
        }
      }, 300);
    });
  }

  function renderSearch(query) {
    setBreadcrumb(["Search", query]);
    clearSourceSelector();
    var q = query.toLowerCase();
    var results = [];

    for (var paradigm of Object.keys(M.paradigms)) {
      var analyses = M.paradigms[paradigm];
      for (var analysis of Object.keys(analyses)) {
        var data = analyses[analysis];
        for (var source of Object.keys(data.figures)) {
          var figs = data.figures[source];
          for (var fig of figs) {
            if (fig.filename.toLowerCase().includes(q) ||
                paradigm.toLowerCase().includes(q) ||
                analysis.toLowerCase().includes(q) ||
                formatName(analysis).toLowerCase().includes(q)) {
              results.push({ type: "figure", paradigm: paradigm, analysis: analysis, source: source, item: fig });
            }
          }
        }
      }
    }

    var html = '<h2 class="section-header">Search: "' + escapeHtml(query) + '"</h2>';
    html += '<p class="search-results-header">' + results.length + ' result(s)</p>';

    if (results.length > 0) {
      var figItems = results.filter(function (r) { return r.type === "figure"; }).map(function (r) { return r.item; });
      html += renderFigureGrid(figItems, PAGE_SIZE);
    }

    setContent(html);
    initLightbox();
  }

  /* ── Figure Grid ── */
  function renderFigureGrid(figs, limit) {
    if (!figs || figs.length === 0) {
      return '<div class="empty-state"><p>No figures</p></div>';
    }
    var show = Math.min(figs.length, limit);
    var html = '<div class="figure-grid">';
    for (var i = 0; i < show; i++) {
      var fig = figs[i];
      html += '<a href="' + fig.path + '" class="glightbox figure-card" data-gallery="gallery">';
      html += '<img src="' + fig.thumb + '" alt="' + escapeHtml(fig.filename) + '" loading="lazy">';
      html += '<div class="caption">' + escapeHtml(fig.filename) + '</div>';
      html += "</a>";
    }
    html += "</div>";

    if (figs.length > limit) {
      html += '<button class="show-more-btn" onclick="window._showMore(this)" data-figs=\'' +
        JSON.stringify(figs.slice(limit)).replace(/'/g, "&#39;") +
        "'>Show " + (figs.length - limit) + " more</button>";
    }
    return html;
  }

  window._showMore = function (btn) {
    try {
      var extra = JSON.parse(btn.getAttribute("data-figs"));
      var grid = btn.previousElementSibling;
      for (var fig of extra) {
        var a = document.createElement("a");
        a.href = fig.path;
        a.className = "glightbox figure-card";
        a.setAttribute("data-gallery", "gallery");
        a.innerHTML = '<img src="' + fig.thumb + '" alt="' + escapeHtml(fig.filename) +
          '" loading="lazy"><div class="caption">' + escapeHtml(fig.filename) + '</div>';
        grid.appendChild(a);
      }
      btn.remove();
      initLightbox();
    } catch (e) {
      console.error("Show more error:", e);
    }
  };

  /* ── Comparison Grid ── */
  function renderComparisonGrid(data, sources) {
    var html = '<div class="comparison-grid">';
    for (var source of sources) {
      html += '<div class="comparison-column"><h3>' + escapeHtml(source) + '</h3>';
      html += renderFigureGrid(data.figures[source] || [], PAGE_SIZE);
      html += "</div>";
    }
    html += "</div>";
    return html;
  }

  /* ── Source Selector ── */
  function renderSourceSelector(sources, current, onChange) {
    var el = document.getElementById("source-selector");
    var html = "<label>Source: <select id='source-select'>";
    for (var s of sources) {
      var sel = s === current ? " selected" : "";
      html += '<option value="' + escapeHtml(s) + '"' + sel + '>' + escapeHtml(s) + '</option>';
    }
    if (sources.length > 1) {
      html += '<option value="__compare__">Compare All</option>';
    }
    html += "</select></label>";
    el.innerHTML = html;

    document.getElementById("source-select").addEventListener("change", function (e) {
      onChange(e.target.value);
    });
  }

  function clearSourceSelector() {
    document.getElementById("source-selector").innerHTML = "";
  }

  /* ── Tables (inline from manifest — no fetch needed) ── */
  function bindTableToggles(tables) {
    document.querySelectorAll(".table-toggle").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var id = btn.getAttribute("data-table-id");
        var idx = parseInt(btn.getAttribute("data-table-idx"), 10);
        var container = document.getElementById(id);

        if (container.style.display === "none") {
          container.style.display = "block";
          btn.classList.add("expanded");
          if (!container.innerHTML.trim()) {
            renderInlineTable(tables[idx], container);
          }
        } else {
          container.style.display = "none";
          btn.classList.remove("expanded");
        }
      });
    });
  }

  function renderInlineTable(tbl, container) {
    if (!tbl || !tbl.headers || tbl.headers.length === 0) {
      container.innerHTML = "<p style='padding:10px'>Empty table</p>";
      return;
    }

    var headers = tbl.headers;
    var rows = tbl.rows;

    // Determine which columns to hide (diagnostic/model-fit columns)
    var hideCols = computeHiddenColumns(headers);

    // Format headers for display
    var html = "<table><thead><tr>";
    for (var ci = 0; ci < headers.length; ci++) {
      if (hideCols[ci]) continue;
      html += '<th>' + escapeHtml(formatColumnHeader(headers[ci])) + '<span class="sort-indicator"></span></th>';
    }
    html += "</tr></thead><tbody>";

    var sigIdx = headers.findIndex(function (h) {
      return h.toLowerCase() === "significant";
    });

    for (var row of rows) {
      var isSig = sigIdx >= 0 && row[sigIdx] && row[sigIdx].toUpperCase() === "TRUE";
      html += '<tr' + (isSig ? ' class="significant"' : '') + '>';
      for (var ci = 0; ci < row.length; ci++) {
        if (hideCols[ci]) continue;
        html += '<td>' + formatCellValue(row[ci], headers[ci]) + '</td>';
      }
      html += "</tr>";
    }
    html += "</tbody></table>";
    if (tbl.truncated) {
      html += '<p style="padding:8px 10px;font-size:12px;color:var(--text-muted)">Showing ' +
        rows.length + ' of ' + tbl.total_rows + ' rows</p>';
    }
    container.innerHTML = html;

    var table = container.querySelector("table");
    if (table && window.Tablesort) {
      new Tablesort(table);
    }
  }

  /**
   * Determine which columns to hide for cleaner presentation.
   * Returns an array of booleans (true = hidden).
   */
  function computeHiddenColumns(headers) {
    var lowerHeaders = headers.map(function (h) { return h.toLowerCase().replace(/"/g, ""); });
    var hide = new Array(headers.length).fill(false);

    // Always hide these diagnostic/redundant columns
    var alwaysHide = [
      "converged", "singular", "convergence",
      "aic_spatial", "bic_spatial", "aic_nonspatial", "bic_nonspatial", "aic_improvement",
      "sig_label",
    ];

    for (var i = 0; i < lowerHeaders.length; i++) {
      if (alwaysHide.indexOf(lowerHeaders[i]) >= 0) {
        hide[i] = true;
      }
    }

    return hide;
  }

  /**
   * Format a column header for display.
   */
  function formatColumnHeader(header) {
    // Strip surrounding quotes
    var h = header.replace(/^"|"$/g, "");

    // Special header renames
    var renames = {
      "group_f": "Group F",
      "group_p": "Group p",
      "roi_f": "ROI F",
      "roi_p": "ROI p",
      "interaction_f": "Interaction F",
      "interaction_p": "Interaction p",
      "group_q": "Group q (FDR)",
      "group_significant": "Group Sig.",
      "interaction_q": "Interaction q (FDR)",
      "interaction_significant": "Interact. Sig.",
      "n_a": "N (A)",
      "n_b": "N (B)",
      "n_rois": "N ROIs",
      "n_regions": "N Regions",
      "group_a": "Group A",
      "group_b": "Group B",
      "measure_type": "Type",
      "dv": "Measure",
      "t_ratio": "t",
      "t_value": "t",
      "p_value": "p",
      "q_value": "q (FDR)",
      "hedges_g": "Hedges' g",
      "std_error": "SE",
      "estimated_range_mm": "Range (mm)",
      "mean_t": "Mean |t|",
      "max_abs_t": "Max |t|",
      "mean_hedges_g": "Mean |g|",
      "max_abs_hedges_g": "Max |g|",
      "n_nominal_sig": "N sig. (uncorr.)",
      "n_vertices": "N Vertices",
      "cluster_stat": "Cluster Stat",
      "peak_t": "Peak t",
      "p_corrected": "p (corrected)",
      "cluster_id": "Cluster",
      "vertex_idx": "Vertex",
      "conn_metric": "Connectivity",
      "graph_metric": "Graph Metric",
      "p_fdr": "p (FDR)",
      "emmean_a": "EMM (A)",
      "emmean_b": "EMM (B)",
      "mean_a": "Mean (A)",
      "mean_b": "Mean (B)",
      "sd_a": "SD (A)",
      "sd_b": "SD (B)",
      "t_stat": "t",
      "observed_diff": "Diff",
    };

    var lower = h.toLowerCase();
    if (renames[lower]) return renames[lower];

    // Default: apply formatName
    return formatName(h);
  }

  /**
   * Format a cell value for display.
   */
  function formatCellValue(value, header) {
    if (value === null || value === undefined || value === "") {
      return '<span style="color:var(--text-muted)">—</span>';
    }

    var str = String(value).replace(/^"|"$/g, ""); // strip quotes
    var headerLower = header.toLowerCase().replace(/^"|"$/g, "");

    // Format contrast names: "30mgkg_vs_Vehicle" → "AUT00206 (30 mg/kg) vs Vehicle"
    if (headerLower === "contrast") {
      return escapeHtml(formatContrast(str));
    }

    // Format group names
    if (headerLower === "group_a" || headerLower === "group_b" || headerLower === "group") {
      return escapeHtml(formatGroupName(str));
    }

    // Format measure names (e.g. "itc_40hz" → "ITC 40 Hz")
    if (headerLower === "measure" || headerLower === "dv" || headerLower === "measure_type") {
      return escapeHtml(formatMeasureName(str));
    }

    // Format band names
    if (headerLower === "band") {
      return escapeHtml(formatName(str));
    }

    // Format metric names
    if (headerLower === "metric" || headerLower === "graph_metric" || headerLower === "conn_metric") {
      return escapeHtml(formatName(str));
    }

    // Boolean display
    if (headerLower === "significant" || headerLower === "group_significant" || headerLower === "interaction_significant") {
      var upper = str.toUpperCase();
      if (upper === "TRUE") return '<strong style="color:#4CAF50">Yes</strong>';
      if (upper === "FALSE") return '<span style="color:var(--text-muted)">No</span>';
    }

    // Numeric formatting
    var num = parseFloat(str);
    if (!isNaN(num) && isFinite(num) && str.match(/^-?\d*\.?\d+(?:e[+-]?\d+)?$/i)) {
      return escapeHtml(formatNumber(num, headerLower));
    }

    return escapeHtml(str);
  }

  /**
   * Format a contrast string for display.
   * "30mgkg_vs_Vehicle" → "AUT00206 (30 mg/kg) vs Vehicle"
   */
  function formatContrast(str) {
    var parts = str.split("_vs_");
    if (parts.length === 2) {
      return formatGroupName(parts[0]) + " vs " + formatGroupName(parts[1]);
    }
    return formatName(str);
  }

  /**
   * Format a group name for display.
   */
  function formatGroupName(name) {
    var lower = name.toLowerCase();
    if (GROUP_LABELS[lower]) return GROUP_LABELS[lower];
    return name;
  }

  /**
   * Format measure names like "itc_40hz" → "ITC 40 Hz", "stp_onset" → "STP Onset"
   */
  function formatMeasureName(str) {
    // Split on underscores and format each part
    return str.split("_").map(function (part) {
      var lower = part.toLowerCase();
      if (ACRONYMS[lower]) return ACRONYMS[lower];
      var hzMatch = lower.match(/^(\d+)(hz)$/);
      if (hzMatch) return hzMatch[1] + " Hz";
      return part.charAt(0).toUpperCase() + part.slice(1);
    }).join(" ");
  }

  /**
   * Format a number based on context (header name).
   */
  function formatNumber(num, headerLower) {
    // p-values: show 3-4 significant digits, scientific notation for very small
    if (headerLower.match(/^p$|^p_|_p$|p_value|p_corrected|q_value|group_q|interaction_q|p_fdr/)) {
      if (num < 0.001) return num.toExponential(2);
      return num.toFixed(4);
    }

    // F-statistics, t-statistics
    if (headerLower.match(/^f$|_f$|group_f|roi_f|interaction_f|^t$|t_ratio|t_value|t_stat|peak_t|mean_t|max_abs_t|cluster_stat/)) {
      return num.toFixed(3);
    }

    // Effect sizes (hedges_g, etc.)
    if (headerLower.match(/hedges_g|mean_hedges_g|max_abs_hedges_g|cohen/)) {
      return num.toFixed(3);
    }

    // Estimates, means, SEs, coefficients
    if (headerLower.match(/estimate|coefficient|std_error|^se$|emmean|^mean|^sd/)) {
      return num.toFixed(4);
    }

    // Degrees of freedom
    if (headerLower.match(/^df$/)) {
      return Math.abs(num - Math.round(num)) < 0.01 ? num.toFixed(0) : num.toFixed(1);
    }

    // AIC/BIC
    if (headerLower.match(/^aic|^bic/)) {
      return num.toFixed(1);
    }

    // Integers (counts)
    if (headerLower.match(/^n$|^n_|n_edges|n_vertices|n_rois|n_regions|n_nominal|n_sig|cluster_id|vertex_idx|n_permutations/)) {
      return Math.abs(num - Math.round(num)) < 0.01 ? num.toFixed(0) : num.toFixed(2);
    }

    // Default: 4 significant figures
    if (Math.abs(num) >= 100) return num.toFixed(1);
    if (Math.abs(num) >= 1) return num.toFixed(3);
    if (Math.abs(num) >= 0.001) return num.toFixed(4);
    return num.toExponential(2);
  }

  /**
   * Format table filename for display.
   * "evoked_omnibus.csv" → "Evoked Omnibus"
   */
  function formatTableFilename(filename) {
    var name = filename.replace(/\.csv$/i, "");
    return formatName(name);
  }

  function initTableSort() {
    if (!window.Tablesort) return;
    document.querySelectorAll(".table-container table").forEach(function (table) {
      new Tablesort(table);
    });
  }

  /* ── Lightbox ── */
  function initLightbox() {
    if (lightbox) { lightbox.destroy(); }
    if (window.GLightbox) {
      lightbox = GLightbox({
        selector: ".glightbox",
        touchNavigation: true,
        loop: true,
        zoomable: true,
        draggable: true,
      });
    }
  }

  /* ── Theme ── */
  function initThemeToggle() {
    var saved = localStorage.getItem("theme");
    if (saved) {
      document.documentElement.setAttribute("data-theme", saved);
    } else if (window.matchMedia && window.matchMedia("(prefers-color-scheme: light)").matches) {
      document.documentElement.setAttribute("data-theme", "light");
    }

    document.getElementById("theme-toggle").addEventListener("click", function () {
      var current = document.documentElement.getAttribute("data-theme");
      var next = current === "dark" ? "light" : "dark";
      document.documentElement.setAttribute("data-theme", next);
      localStorage.setItem("theme", next);
    });
  }

  /* ── Keyboard ── */
  function initKeyboard() {
    document.addEventListener("keydown", function (e) {
      if (e.key === "/" && document.activeElement.tagName !== "INPUT") {
        e.preventDefault();
        document.getElementById("search-input").focus();
      }
      if (e.key === "Escape") {
        document.getElementById("search-input").blur();
      }
    });
  }

  /* ── Helpers ── */
  function setBreadcrumb(parts) {
    var el = document.getElementById("breadcrumb");
    el.innerHTML = parts.map(function (p, i) {
      return (i > 0 ? "<span>&rsaquo;</span>" : "") + escapeHtml(p);
    }).join("");
  }

  function setContent(html) {
    document.getElementById("figures-section").innerHTML = html;
    document.getElementById("tables-section").innerHTML = "";
    document.getElementById("summary-section").innerHTML = "";
  }

  function formatName(slug) {
    return slug
      .replace(/_/g, " ")
      .split(" ")
      .map(function (word) {
        var lower = word.toLowerCase();
        if (ACRONYMS[lower]) return ACRONYMS[lower];
        // Handle "40hz" → "40 Hz", "80hz" → "80 Hz"
        var hzMatch = lower.match(/^(\d+)(hz)$/);
        if (hzMatch) return hzMatch[1] + " Hz";
        return word.charAt(0).toUpperCase() + word.slice(1);
      })
      .join(" ");
  }

  function escapeHtml(str) {
    if (!str) return "";
    return String(str).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }
})();

/* ============================================================
   main.js — 首屏图谱收敛动效、滚动入场、跑马灯
   图谱动效是这页的记忆点：节点从「散落的笔记」收敛成
   「一条可以走的学习路径」—— 把产品价值主张画出来。
   ============================================================ */

(function () {
  "use strict";

  var REDUCED = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* ---------------------------------------------------------- *
   * 1. 首屏图谱：散点 → 学习路径
   *
   * 实现说明：
   * - 8 个主路径节点（朱砂）+ 18 个背景节点（墨线），全部用 JS 生成；
   * - 每个节点有一对坐标：散点位（随机但定种子，保证每次打开构图稳定）
   *   与目标位（蛇形路径 / 背景星座位）；
   * - 入场时先把节点放在散点位，下一帧再切到目标位，交给 CSS 过渡；
   * - 连线用 pathLength=1 + stroke-dashoffset 描画，依次出现；
   * - prefers-reduced-motion：直接画最终态，不做任何动画。
   * ---------------------------------------------------------- */

  var NS = "http://www.w3.org/2000/svg";
  var svg = document.getElementById("heroGraph");
  if (svg) buildGraph(svg);

  function mulberry(seed) {          // 定种子伪随机：构图可复现
    return function () {
      seed |= 0; seed = (seed + 0x6D2B79F5) | 0;
      var t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  function buildGraph(svg) {
    var W = 680, H = 560;   // 与容器（约 1:1 到 1.2:1）接近，减少 letterbox 空旷感
    svg.setAttribute("viewBox", "0 0 " + W + " " + H);
    svg.setAttribute("role", "img");
    svg.setAttribute("aria-label",
      "示意图：散落的笔记节点逐渐连线，收敛成一条学习路径");

    var rand = mulberry(20261017);

    // 主路径：8 个节点走一条 S 形蛇形线 —— 这就是"学习主线"
    var pathLabels = ["索引", "B+ 树", "最左前缀", "查询优化", "执行计划",
                      "回表", "覆盖索引", "调优清单"];
    var pathNodes = [];
    var cols = 4, rows = 2;
    for (var i = 0; i < pathLabels.length; i++) {
      var r = Math.floor(i / cols), c = i % cols;
      if (r % 2 === 1) c = cols - 1 - c;         // 蛇形折返
      pathNodes.push({
        label: pathLabels[i],
        tx: 90 + c * (W - 200) / (cols - 1),
        ty: 150 + r * (H - 300) + (r === 0 ? 0 : 40),
        main: true
      });
    }

    // 背景节点：散布四周的星座，收敛后留在原地当作"知识星云"
    var bgNodes = [];
    for (var j = 0; j < 18; j++) {
      bgNodes.push({
        tx: 60 + rand() * (W - 120),
        ty: 40 + rand() * (H - 80),
        main: false
      });
    }

    var all = pathNodes.concat(bgNodes);

    // 连线：主路径 7 条（朱砂粗线）+ 背景稀疏连线（发丝线）
    var edges = [];
    for (var k = 0; k < pathNodes.length - 1; k++) {
      edges.push({ a: pathNodes[k], b: pathNodes[k + 1], main: true });
    }
    var bgLinks = 0;
    while (bgLinks < 14) {
      var a = bgNodes[Math.floor(rand() * bgNodes.length)];
      var b = rand() < 0.4
        ? pathNodes[Math.floor(rand() * pathNodes.length)]
        : bgNodes[Math.floor(rand() * bgNodes.length)];
      if (a !== b) { edges.push({ a: a, b: b, main: false }); bgLinks++; }
    }

    var edgeEls = edges.map(function (e, idx) {
      var line = document.createElementNS(NS, "line");
      line.setAttribute("x1", e.a.tx); line.setAttribute("y1", e.a.ty);
      line.setAttribute("x2", e.b.tx); line.setAttribute("y2", e.b.ty);
      line.setAttribute("stroke", e.main ? "#c13b2a" : "rgba(28,24,19,0.28)");
      line.setAttribute("stroke-width", e.main ? 2.4 : 1);
      line.setAttribute("pathLength", "1");
      line.setAttribute("class", "gedge");
      line.style.transitionDelay = (idx * 90) + "ms";
      svg.appendChild(line);
      return line;
    });

    var nodeEls = all.map(function (n, idx) {
      var g = document.createElementNS(NS, "g");
      g.setAttribute("class", "gnode");
      var drift = document.createElementNS(NS, "g");
      drift.setAttribute("class", "drift");
      drift.style.animationDuration = (5.5 + (idx % 5) * 0.9) + "s";
      drift.style.animationDelay = (-idx * 0.7) + "s";

      var c = document.createElementNS(NS, "circle");
      c.setAttribute("r", n.main ? 9 : 3.2);
      c.setAttribute("fill", n.main ? "#c13b2a" : "#f5f1e8");
      c.setAttribute("stroke", n.main ? "#9c2c1f" : "rgba(28,24,19,0.55)");
      c.setAttribute("stroke-width", n.main ? 2 : 1.2);
      drift.appendChild(c);

      if (n.main) {
        var inner = document.createElementNS(NS, "circle");   // 朱砂双圈
        inner.setAttribute("r", 4);
        inner.setAttribute("fill", "#f5f1e8");
        drift.appendChild(inner);

        var t = document.createElementNS(NS, "text");
        t.textContent = n.label;
        t.setAttribute("y", -18);
        t.setAttribute("text-anchor", "middle");
        t.setAttribute("font-size", "15");
        t.setAttribute("font-family", "'Noto Serif SC','Songti SC',serif");
        t.setAttribute("font-weight", "700");
        t.setAttribute("fill", "#1c1813");
        drift.appendChild(t);
      }

      g.appendChild(drift);
      svg.appendChild(g);

      // 散点位：以目标位为中心向外散开，附带一点整体漂移
      var angle = rand() * Math.PI * 2;
      var dist = 140 + rand() * 220;
      n.sx = Math.min(W - 30, Math.max(30, n.tx + Math.cos(angle) * dist));
      n.sy = Math.min(H - 30, Math.max(30, n.ty + Math.sin(angle) * dist));

      return { el: g, node: n, idx: idx };
    });

    function place(atScatter) {
      nodeEls.forEach(function (item) {
        var n = item.node;
        item.el.setAttribute("transform",
          "translate(" + (atScatter ? n.sx : n.tx) + "," + (atScatter ? n.sy : n.ty) + ")");
        item.el.style.transitionDelay = (item.idx * 55) + "ms";
      });
    }

    if (REDUCED) {                       // 减少动效：直接终态
      nodeEls.forEach(function (item) {
        item.el.style.transition = "none";
        item.el.setAttribute("transform",
          "translate(" + item.node.tx + "," + item.node.ty + ")");
      });
      edgeEls.forEach(function (l) {
        l.style.transition = "none";
        l.style.strokeDashoffset = "0";
      });
      return;
    }

    place(true);                         // 先放到散点位
    requestAnimationFrame(function () {  // 下一帧切目标位，触发过渡
      requestAnimationFrame(function () {
        place(false);
        edgeEls.forEach(function (l) {
          l.style.strokeDashoffset = "0";
        });
      });
    });
  }

  /* ---------------------------------------------------------- *
   * 2. 滚动入场：IntersectionObserver，只动 opacity/translateY
   * ---------------------------------------------------------- */

  var revealEls = document.querySelectorAll("[data-reveal]");
  if (REDUCED || !("IntersectionObserver" in window)) {
    revealEls.forEach(function (el) { el.classList.add("in"); });
  } else {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          var el = entry.target;
          // 同组兄弟元素错峰 90ms
          var delay = Number(el.getAttribute("data-reveal-delay") || 0);
          setTimeout(function () { el.classList.add("in"); }, delay);
          io.unobserve(el);
        }
      });
    }, { threshold: 0.18, rootMargin: "0px 0px -8% 0px" });
    revealEls.forEach(function (el) { io.observe(el); });
  }

  /* ---------------------------------------------------------- *
   * 3. 跑马灯：复制一份内容实现无缝循环（宽度取半即循环点）
   * ---------------------------------------------------------- */

  var track = document.querySelector(".ticker-track");
  if (track && !track.dataset.cloned) {
    track.innerHTML += track.innerHTML;   // 复制一份
    track.dataset.cloned = "1";
  }

  /* ---------------------------------------------------------- *
   * 4. 「进入项目」的目标地址
   *
   * 默认写死在 index.html 里（本地开发 http://127.0.0.1:5173）。
   * 部署到别的机器/端口时不改文件，只要给链接加参数：
   *     index.html?app=192.168.1.8:5173
   * 也可以在上层页面预先定义 window.KG_APP_URL。
   * ---------------------------------------------------------- */

  var params = new URLSearchParams(window.location.search);
  var appUrl = params.get("app") || window.KG_APP_URL;
  if (appUrl) {
    if (!/^https?:\/\//i.test(appUrl)) appUrl = "http://" + appUrl;
    document.querySelectorAll("[data-app-link]").forEach(function (a) {
      a.setAttribute("href", appUrl);
    });
  }
})();

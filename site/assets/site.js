// Two small helpers; every page works without them.
(function () {
  "use strict";
  var root = document.documentElement;
  root.classList.add("js");
  var lang = (root.lang || "en").slice(0, 2);
  var words = {
    en: { menu: "Menu", copy: "Copy", copied: "Copied" },
    tr: { menu: "Menü", copy: "Kopyala", copied: "Kopyalandı" },
    zh: { menu: "菜单", copy: "复制", copied: "已复制" }
  }[lang] || { menu: "Menu", copy: "Copy", copied: "Copied" };

  // The menu button on narrow screens.
  var nav = document.querySelector(".site-nav");
  var btn = document.querySelector(".menu-btn");
  if (nav && btn) {
    btn.textContent = words.menu;
    btn.addEventListener("click", function () {
      var open = nav.classList.toggle("open");
      btn.setAttribute("aria-expanded", open ? "true" : "false");
    });
  }

  // A copy button on every command block. Lines starting with "#" and the text after " # " are comments
  // in the shell, so copying the whole block is always safe to paste.
  if (!navigator.clipboard) return;
  document.querySelectorAll("pre > code").forEach(function (code) {
    var b = document.createElement("button");
    b.type = "button";
    b.className = "copy";
    b.textContent = words.copy;
    b.addEventListener("click", function () {
      navigator.clipboard.writeText(code.innerText.replace(/\s+$/, "") + "\n").then(function () {
        b.textContent = words.copied;
        setTimeout(function () { b.textContent = words.copy; }, 1500);
      });
    });
    code.parentNode.appendChild(b);
  });
})();

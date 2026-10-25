const font = '"Atkinson Hyperlegible Next", Verdana, sans-serif';

function theme({ ink, panel, rule, tint, signal }) {
  return {
    theme: "base",
    fontFamily: font,
    flowchart: { curve: "linear", padding: 12, nodeSpacing: 36, rankSpacing: 44 },
    sequence: { actorMargin: 40, mirrorActors: false },
    themeVariables: {
      fontFamily: font,
      fontSize: "14px",
      background: panel,
      mainBkg: panel,
      primaryColor: panel,
      primaryTextColor: ink,
      primaryBorderColor: ink,
      secondaryColor: tint,
      tertiaryColor: tint,
      lineColor: ink,
      textColor: ink,
      clusterBkg: tint,
      clusterBorder: rule,
      titleColor: ink,
      edgeLabelBackground: panel,
      nodeBorder: ink,
      actorBkg: panel,
      actorBorder: ink,
      actorTextColor: ink,
      actorLineColor: rule,
      signalColor: ink,
      signalTextColor: ink,
      labelBoxBkgColor: tint,
      labelBoxBorderColor: rule,
      labelTextColor: ink,
      loopTextColor: ink,
      noteBkgColor: tint,
      noteBorderColor: rule,
      noteTextColor: ink,
      activationBkgColor: tint,
      activationBorderColor: ink,
      stateBkg: panel,
      stateBorder: ink,
      transitionColor: ink,
      transitionLabelColor: ink,
      altBackground: tint,
      linkColor: signal,
    },
  };
}

export const mermaidConfig = theme({ ink: "#15181b", panel: "#e7e9e6", rule: "#c1c3c2", tint: "#dadcd9", signal: "#2d5b8c" });
export const mermaidDarkConfig = theme({ ink: "#e7e9e6", panel: "#1c2024", rule: "#424548", tint: "#2a2e32", signal: "#79a9da" });

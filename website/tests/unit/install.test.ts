import { existsSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { DISTRIBUTION_NAME } from "../../src/config/brand";
import { INSTALL_SITE, ON_PYPI, commandPieces, installChannels } from "../../src/lib/install";

const publicFile = (name: string) => fileURLToPath(new URL(`../../public/${name}`, import.meta.url));

describe("the install commands", () => {
  it("offer only the one-line installers until the first PyPI release", () => {
    expect(installChannels(false).map((channel) => channel.label)).toEqual(["macOS and Linux", "Windows"]);
    expect(installChannels(true).map((channel) => channel.label)).toEqual(["macOS and Linux", "Windows", "uv", "pipx"]);
    expect(installChannels()).toEqual(installChannels(ON_PYPI));
  });

  it("fill in the site and the distribution and leave no placeholder", () => {
    const commands = installChannels(true).map((channel) => channel.command);
    expect(commands).toEqual([`curl -LsSf ${INSTALL_SITE}/install.sh | sh`, `irm ${INSTALL_SITE}/install.ps1 | iex`, `uv tool install ${DISTRIBUTION_NAME}`, `pipx install ${DISTRIBUTION_NAME}`]);
    for (const command of commands) expect(command).not.toMatch(/[{}]/);
  });

  it("point at installers the site serves, which name the same site", () => {
    expect(INSTALL_SITE).toBe("https://sohan-bhat.github.io/OpenHAL");
    for (const name of ["install.sh", "install.ps1"]) expect(existsSync(publicFile(name)), name).toBe(true);
    expect(readFileSync(publicFile("install.sh"), "utf8")).toContain(`SITE="${INSTALL_SITE}"`);
  });

  it("mark the Windows channel with its own prompt", () => {
    const windows = installChannels().filter((channel) => channel.platform === "windows");
    expect(windows.map((channel) => [channel.label, channel.prompt])).toEqual([["Windows", "PS>"]]);
    expect(installChannels()[0]).toMatchObject({ label: "macOS and Linux", prompt: "$" });
  });

  it("break a command only between words and after a slash, and keep every character", () => {
    for (const { command } of installChannels(true)) {
      const pieces = commandPieces(command);
      expect(pieces.map((word) => word.join("")).join(" ")).toBe(command);
      for (const word of pieces) for (const piece of word) expect(piece.startsWith("/"), `${command} ${piece}`).toBe(false);
    }
    expect(commandPieces(`curl -LsSf ${INSTALL_SITE}/install.sh | sh`)).toEqual([["curl"], ["-LsSf"], ["https://", "sohan-bhat.github.io/", "OpenHAL/", "install.sh"], ["| sh"]]);
  });
});

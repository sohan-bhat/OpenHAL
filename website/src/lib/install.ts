import { DISTRIBUTION_NAME } from "../config/brand";
import install from "../config/install.json" with { type: "json" };
import { REPOSITORY_URL } from "../config/repo.mjs";

/** One way to install OpenHAL, as the hero's install box shows it. */
export interface InstallChannel {
  id: string;
  label: string;
  prompt: string;
  command: string;
  platform?: string;
}

/** Where the one-line installers are served, the site's own address. */
export const INSTALL_SITE: string = install.site;

/** True from the first PyPI release on, the one value the release step changes in install.json. */
export const ON_PYPI: boolean = install.onPyPI;

/** A command from install.json with its {site}, {distribution} and {repository} filled in. */
export function fillCommand(template: string): string {
  return template.replaceAll("{site}", INSTALL_SITE).replaceAll("{distribution}", DISTRIBUTION_NAME).replaceAll("{repository}", REPOSITORY_URL);
}

/**
 * The channels the hero offers, in install.json's order. A channel with a beforePyPI command
 * installs the distribution from PyPI, so the hero leaves it out until onPyPI is true.
 */
export function installChannels(onPyPI: boolean = ON_PYPI): InstallChannel[] {
  return install.channels
    .filter((channel) => onPyPI || !("beforePyPI" in channel))
    .map((channel) => ({
      id: channel.id,
      label: channel.label,
      prompt: channel.prompt,
      command: fillCommand(channel.command),
      ...("platform" in channel ? { platform: channel.platform } : {}),
    }));
}

/** The demo's commands, as the home page and the README show them. */
export interface DemoCommands {
  installed: string;
  withoutInstall?: string;
}

/**
 * The demo after the install, and the uvx command that runs the demo without an install. uvx
 * fetches the distribution from PyPI, so the uvx command shows only once onPyPI is true, the way
 * the hero leaves out its uv and pipx tabs until then.
 */
export function demoCommands(onPyPI: boolean = ON_PYPI): DemoCommands {
  return {
    installed: fillCommand(install.demo.command),
    ...(onPyPI ? { withoutInstall: fillCommand(install.demo.fromPyPI) } : {}),
  };
}

/**
 * The pieces a command wraps between, so a narrow screen breaks a line only between words or
 * after a slash in an address, and a pipe stays with the command after the pipe.
 */
export function commandPieces(command: string): string[][] {
  const words: string[] = [];
  for (const word of command.split(" ")) {
    if (words.length && words[words.length - 1] === "|") words[words.length - 1] = `| ${word}`;
    else words.push(word);
  }
  return words.map((word) => (word.includes("://") ? word.split(/(?<=\/)(?=[^/])/) : [word]));
}

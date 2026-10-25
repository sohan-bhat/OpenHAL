export const REPOSITORY_URL = "https://github.com/sohan-bhat/OpenHAL";
export const REPOSITORY_DIR = "OpenHAL";
export const DEFAULT_BRANCH = "main";

export function editUrl(repoPath) {
  return `${REPOSITORY_URL}/edit/${DEFAULT_BRANCH}/${repoPath}`;
}

export function sourceUrl(repoPath) {
  return `${REPOSITORY_URL}/blob/${DEFAULT_BRANCH}/${repoPath}`;
}

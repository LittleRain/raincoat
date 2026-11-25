/**
 * Injected prelude for the "Recent" section.
 *
 * `scripts/build.mjs` inlines this file verbatim into the patched copy of
 * @deepseek-ai/dsh-client-ui-workspace/lib/client.js, so it runs inside that
 * bundle's module scope and may call the module-local helpers that already
 * exist there: mainSessionId, sessionVisible, sessionNode.
 *
 * Keep this file plain ES2020 with no imports and no JSX.
 */
const RECENT_KEY = `__recent__`;
const RECENT_LIMIT = 8;

function deriveRecentSection(list, rowState, statuses, pinned, archived, groupExpansion) {
  const current = mainSessionId(list);
  const items = [];
  for (const id of list.ids) {
    const session = list.byId[id];
    if (session === undefined || session.blank) continue;
    if (!sessionVisible(session, current, archived, rowState.archivedFilter)) continue;
    items.push(session);
  }
  if (items.length === 0) return undefined;
  items.sort((a, b) => (b.updatedAt ?? 0) - (a.updatedAt ?? 0));
  const top = items.slice(0, RECENT_LIMIT);
  return {
    key: RECENT_KEY,
    workspaceId: undefined,
    cwd: undefined,
    createdAt: 0,
    label: `__recent__`,
    sessionCount: items.length,
    expanded: groupExpansion[RECENT_KEY] !== false,
    containsCurrent: false,
    sessions: top.map((session) => sessionNode(session, list, statuses, pinned, archived)),
  };
}

function withRecentSection(groups, list, rowState, statuses, groupExpansion, manualOrder, nested) {
  // Hidden in manual ordering (the list is the user order) and in the workspace
  // tree (sessions already nest under their workspace).
  if (manualOrder === true || nested === true) return groups;
  if (list === undefined || list.ids.length === 0) return groups;
  const pinned = new Set(rowState.pinnedSessionIds);
  const archived = new Set(rowState.archivedSessionIds);
  const recent = deriveRecentSection(list, rowState, statuses, pinned, archived, groupExpansion ?? {});
  return recent === undefined ? groups : [recent, ...groups];
}

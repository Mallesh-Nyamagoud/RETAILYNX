// Keep SOH usable when background refreshes fail but React Query has cached data.
export function canLoadSohSummary(datesQuery, start, end) {
  return Boolean(start && end && datesQuery.data);
}

export function getSohSourceError(datesQuery) {
  return (!datesQuery.data && datesQuery.error) || null;
}

export function hasSohSourceRefreshFailure(datesQuery) {
  return Boolean(datesQuery.data && datesQuery.isError);
}

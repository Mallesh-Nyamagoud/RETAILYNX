// Keep SOH usable when background refreshes fail but React Query has cached data.
export function canLoadSohSummary(datesQuery, filtersQuery, start, end) {
  return Boolean(start && end && datesQuery.data && filtersQuery.data);
}

export function getSohSourceError(datesQuery, filtersQuery) {
  return (!datesQuery.data && datesQuery.error) || (!filtersQuery.data && filtersQuery.error) || null;
}

export function hasSohSourceRefreshFailure(datesQuery, filtersQuery) {
  return Boolean((datesQuery.data && datesQuery.isError) || (filtersQuery.data && filtersQuery.isError));
}

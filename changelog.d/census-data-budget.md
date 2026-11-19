### Fixed

- `statcan_census_profile_get_data` stops retrying a slow census request when 30
  seconds of the tool's time limit are left, and says StatCan's census API was
  slow. Three 60-second attempts used to run past the default 120-second limit,
  so the caller got the server's generic timeout instead.

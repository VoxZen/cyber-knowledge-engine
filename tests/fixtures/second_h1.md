# HTTP Status Codes

Three-digit codes a web server returns with every response.

## Classes

- 1xx informational
- 2xx success
- 4xx client error

# Common codes

- 200 OK
- 404 Not Found

1. Check the status code of a page:
   ```bash
   # -i prints the response headers
   curl -i http://<target_ip>/
   ```

## Notes

Codes are grouped by their first digit.

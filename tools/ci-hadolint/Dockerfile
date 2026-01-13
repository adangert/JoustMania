FROM hadolint/hadolint:v2.12.0-alpine

# Add wrapper script for easier bulk linting
RUN echo '#!/bin/sh' > /usr/local/bin/lint-all-dockerfiles.sh && \
    echo 'set -e' >> /usr/local/bin/lint-all-dockerfiles.sh && \
    echo 'find /workspace -name "Dockerfile" -type f -exec echo "Linting {}" \; -exec hadolint {} \;' >> /usr/local/bin/lint-all-dockerfiles.sh && \
    chmod +x /usr/local/bin/lint-all-dockerfiles.sh

WORKDIR /workspace
ENTRYPOINT ["/bin/hadolint"]

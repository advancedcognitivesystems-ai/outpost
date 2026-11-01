#!/bin/sh
# Entrypoint of outpost/base, run at every start of the container, whoever starts it:
# prepares cgroups, starts the inner Docker engine, then `outpost boot` starts the proxy and
# runs the init scripts. The container lives as long as the inner engine, which logs to
# /var/log/outpost/dockerd.log.
set -eu

# cgroup v2 nesting, as moby's hack/dind does: move this group's processes into a child group,
# then delegate the controllers, or the inner engine cannot create containers.
if [ -f /sys/fs/cgroup/cgroup.controllers ]; then
  mkdir -p /sys/fs/cgroup/init
  xargs -rn1 < /sys/fs/cgroup/cgroup.procs > /sys/fs/cgroup/init/cgroup.procs 2>/dev/null || true
  sed -e 's/ / +/g' -e 's/^/+/' < /sys/fs/cgroup/cgroup.controllers \
    > /sys/fs/cgroup/cgroup.subtree_control 2>/dev/null || true
fi

# Pid files left by the last run would make the engine refuse to start.
rm -f /var/run/docker.pid /var/run/docker/containerd/containerd.pid
mkdir -p /var/log/outpost
dockerd > /var/log/outpost/dockerd.log 2>&1 &
dockerd_pid=$!

# Stopping the container stops the inner engine first, which stops the stacks cleanly; the
# container's stop timeout, set by Outpost, gives it the time.
stop() {
  kill -TERM "$dockerd_pid" 2> /dev/null || true
  wait "$dockerd_pid" || true
  exit 0
}
trap stop TERM INT

tries=0
until docker info > /dev/null 2>&1; do
  tries=$((tries + 1))
  if ! kill -0 "$dockerd_pid" 2> /dev/null || [ "$tries" -gt 60 ]; then
    echo "outpost: the inner Docker engine did not start; its log ends with:" >&2
    tail -n 20 /var/log/outpost/dockerd.log >&2 || true
    exit 1
  fi
  sleep 1
done

outpost boot || echo "outpost: boot reported a problem; the container keeps running" >&2

wait "$dockerd_pid"

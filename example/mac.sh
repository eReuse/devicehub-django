for i in /sys/class/net/*; do
    n=${i##*/}
    dev=$(readlink -f "$i/device" 2>/dev/null) || continue
    mac=$(ethtool -P "$n" 2>/dev/null | sed 's/.*: //')
    [ -z "$mac" ] && mac=$(cat "$i/address")
    printf '%s %s %s\n' "$(basename "$dev")" "$n" "$mac"
done

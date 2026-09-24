#!/bin/sh

set -e
set -u
# DEBUG
set -x

do_codeberg_release() {
        release_data='{
  "tag_name":"%s",
  "name":"%s",
  "body":"%s",
  "draft":false,
  "prerelease":false,
  "hide_archive_links":true
}'
        codeberg_post_url='https://codeberg.org/api/v1/repos'
        curl -s \
             -X POST "${codeberg_post_url}/${CODEBERG_USER}/${CODEBERG_REPO}/releases" \
             -H "Authorization: token ${CODEBERG_TOKEN}" \
             -H "Content-Type: application/json" \
             -d "$(printf "${release_data}" \
                          "${VERSION}" "${VERSION}" "${release_message}")"
}

get_next_version() {
        current_year="$(date +'%Y')"
        previous_number=$(git tag --list \
                                  | grep "${current_year}" \
                                  | sed "s/${current_year}\.//" \
                                  | sort -n \
                                  | tail -1)
        number="$(( ${previous_number:-0} + 1 ))"
        VERSION="v$(echo "${current_year}.${number}")"
}

autochangelog() {
        CHANGELOG_CONTENT="$(python ./script-utils/generate-changelog.py)"
        get_next_version

        cat > CHANGELOG.md.new <<EOF
# ${VERSION}

## Highlights

TODO manually

## More details

Merged PRs

<details>
${CHANGELOG_CONTENT}
</details>

$(cat CHANGELOG.md)
EOF
        mv CHANGELOG.md.new CHANGELOG.md
}

main() {
        if [ -n "$(git status --porcelain)" ]; then
                echo "You have uncommitted changes in git"
                exit 1
        fi

        cd "$(dirname "$0")/.."

        # TODO commented, we add highlights
        # autochangelog

        # get unreleased CHANGELOG
        # awk: if find Match (m) the regex (to next heading) just print that
        CHANGELOG_CONTENT="$(awk '/^# /{if(m)exit; m=1} m' CHANGELOG.md)"
        exit 1

        git tag -a "${VERSION}" -m "${CHANGELOG_CONTENT}"

        exit 1

        git push origin "${VERSION}"

        # looks like I should wait some seconds, to ensure release works
        sleep 5

        do_codeberg_release
        # TODO github release

        echo "Released ${VERSION}"
}

main "${@:-}"

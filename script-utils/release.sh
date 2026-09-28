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

main() {
        if [ -n "$(git status --porcelain)" ]; then
                echo "You have uncommitted changes in git"
                exit 1
        fi

        { python ./generate-changelog.py; cat ../CHANGELOG.md; } > ../CHANGELOG.tmp \
                && mv ../CHANGELOG.tmp ../CHANGELOG.md

        cd "$(dirname "$0")/.."


        current_year="$(date +'%Y')"
        previous_number=$(git tag --list \
                                  | grep "${current_year}" \
                                  | sed "s/${current_year}\.//" \
                                  | sort -n \
                                  | tail -1)
        number="$(( ${previous_number:-0} + 1 ))"
        VERSION=$(echo "${current_year}.${number}")

        # awk: if find Match (m) the regex (to next heading) just print that
        CHANGELOG_CONTENT="$(awk '/^# /{if(m)exit; m=1} m' ../CHANGELOG.md)"

        git tag -a "${VERSION}" -m "${CHANGELOG_CONTENT}"

        # git push origin "${VERSION}"

        # looks like I should wait some seconds, to ensure release works
        sleep 5

        # do_codeberg_release

        echo "Released ${VERSION}"
}

main "${@:-}"

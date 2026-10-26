#!/usr/bin/env bash
# Прогон сценария по живому серверу: ./smoke.sh [адрес]
# Перед запуском: uvicorn app.main:app --port 8080
BASE="${1:-http://localhost:8080}"
API="$BASE/api/v1"
U1="Authorization: Bearer user-1"
U2="Authorization: Bearer user-2"
J="Content-Type: application/json"
fail=0

# check <описание> <ожидаемый код> <метод> <url> [заголовки и тело через curl-аргументы]
check() {
  local name="$1" expected="$2"; shift 2
  local out code body
  out=$(curl -s -w '\n%{http_code}' "$@")
  code=$(printf '%s' "$out" | tail -n1)
  body=$(printf '%s' "$out" | sed '$d')
  if [ "$code" = "$expected" ]; then printf 'OK   %s -> %s\n' "$name" "$code"
  else printf 'FAIL %s -> %s (ожидалось %s)\n     %s\n' "$name" "$code" "$expected" "$body"; fail=1; fi
  LAST_BODY="$body"
}
field() { printf '%s' "$LAST_BODY" | python3 -c "import sys,json;print(json.load(sys.stdin)['$1'])"; }

curl -s -X POST "$BASE/debug/reset" >/dev/null

check "без токена"                    401 "$API/catalog/lookup?barcode=0602537284332"
check "плохой штрихкод"               400 -H "$U1" "$API/catalog/lookup?barcode=123"
check "штрихкод не найден"            404 -H "$U1" "$API/catalog/lookup?barcode=1111111111111"
check "Discogs недоступен"            503 -H "$U1" "$API/catalog/lookup?barcode=0000000000000"
check "поиск по штрихкоду"            200 -H "$U1" "$API/catalog/lookup?barcode=0602537284332"

check "Wantlist (подписчик user-2)"   201 -X POST -H "$U2" -H "$J" -d '{"releaseId":1001}' "$API/collection/wantlist"
WANT=$(field id)
check "Wantlist: дубликат"            409 -X POST -H "$U2" -H "$J" -d '{"releaseId":1001}' "$API/collection/wantlist"

check "черновик карточки"             201 -X POST -H "$U1" -H "$J" -d '{"releaseId":1001}' "$API/collection/items"
ITEM=$(field id)
check "подтверждение карточки"        200 -X PATCH -H "$U1" -H "$J" -d '{"mediaCondition":"NM","sleeveCondition":"VG+","confirm":true}' "$API/collection/items/$ITEM"
check "чужую карточку менять нельзя"  403 -X PATCH -H "$U2" -H "$J" -d '{"note":"x"}' "$API/collection/items/$ITEM"

check "ревью до покупки (чужой релиз)" 403 -X POST -H "$U2" -H "$J" -d '{"releaseId":1001,"pros":"Бас"}' "$API/social/reviews"
check "ревью"                         201 -X POST -H "$U1" -H "$J" -d '{"releaseId":1001,"pros":"Глубокий бас","cons":"Шум"}' "$API/social/reviews"
REVIEW=$(field id)
check "ревью: повтор"                 409 -X POST -H "$U1" -H "$J" -d '{"releaseId":1001,"pros":"Ещё"}' "$API/social/reviews"
check "правка ревью"                  200 -X PATCH -H "$U1" -H "$J" -d '{"cons":"Шум пропал"}' "$API/social/reviews/$REVIEW"

check "лот: цена 0"                   400 -X POST -H "$U1" -H "$J" -d "{\"collectionItemId\":$ITEM,\"price\":0,\"currency\":\"RUB\"}" "$API/marketplace/listings"
check "лот создан"                    201 -X POST -H "$U1" -H "$J" -d "{\"collectionItemId\":$ITEM,\"price\":4500,\"currency\":\"RUB\"}" "$API/marketplace/listings"
LISTING=$(field id)
check "лот: экземпляр уже продаётся"  409 -X POST -H "$U1" -H "$J" -d "{\"collectionItemId\":$ITEM,\"price\":4500,\"currency\":\"RUB\"}" "$API/marketplace/listings"

echo "--- уведомления, отправленные подписчикам:"
curl -s "$BASE/debug/notifications"; echo

check "снять лот"                     204 -X DELETE -H "$U1" "$API/marketplace/listings/$LISTING"
check "снять лот повторно"            409 -X DELETE -H "$U1" "$API/marketplace/listings/$LISTING"
check "удалить из Wantlist"           204 -X DELETE -H "$U2" "$API/collection/wantlist/$WANT"

[ $fail = 0 ] && echo "ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ" || { echo "ЕСТЬ ОШИБКИ"; exit 1; }

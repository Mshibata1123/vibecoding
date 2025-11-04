import streamlit as st
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta
import pandas as pd
import base64
import googlemaps
import os
from urllib.parse import quote

# --- 予防接種マスターデータ ---
# ワクチン名、接種回数、推奨接種期間（開始月齢, 基準からの間隔月数）
VACCINES = [
    {'name': 'B型肝炎', 'count': 3, 'periods': [(2, 0), (3, 0), (7, 0)]},
    {'name': 'ロタウイルス', 'count': 2, 'periods': [(2, 0), (3, 0)]}, # ワクチンによる
    {'name': 'ヒブ', 'count': 4, 'periods': [(2, 0), (3, 0), (4, 0), (12, 0)]},
    {'name': '小児用肺炎球菌', 'count': 4, 'periods': [(2, 0), (3, 0), (4, 0), (12, 0)]},
    {'name': '四種混合(DPT-IPV)', 'count': 4, 'periods': [(3, 0), (4, 0), (5, 0), (18, 0)]},
    {'name': 'BCG', 'count': 1, 'periods': [(5, 0)]},
    {'name': 'MR(麻しん風しん混合)', 'count': 2, 'periods': [(12, 0), (60, 0)]}, # 2期は小学校入学前1年間
    {'name': '水痘(みずぼうそう)', 'count': 2, 'periods': [(12, 0), (15, 3)]}, # 2回目は1回目から3ヶ月以上あける
    {'name': '日本脳炎', 'count': 4, 'periods': [(36, 0), (37, 1), (49, 12), (108, 0)]}, # 2期は9歳、3回目は2回目から約1年後
]

def calculate_schedule(birth_date):
    """生年月日から推奨接種スケジュールを計算する"""
    schedule = []
    for vaccine in VACCINES:
        last_shot_date = None
        for i in range(vaccine['count']):
            start_months, interval_months = vaccine['periods'][i]
            
            if i > 0 and interval_months > 0:
                # 2回目以降で間隔が指定されている場合
                base_date = last_shot_date if last_shot_date else birth_date + relativedelta(months=vaccine['periods'][i-1][0])
                recommended_start = base_date + relativedelta(months=interval_months)
            else:
                # 1回目、または月齢で決まる場合
                recommended_start = birth_date + relativedelta(months=start_months)

            # 推奨終了日は、開始日の1ヶ月後とする（簡略化）
            recommended_end = recommended_start + relativedelta(months=1) - timedelta(days=1)
            
            schedule_item = {
                'vaccine_name': f"{vaccine['name']} ({i+1}回目)",
                'recommended_start': recommended_start,
                'recommended_end': recommended_end,
                'status': '未接種'
            }
            schedule.append(schedule_item)
            last_shot_date = recommended_start
            
    schedule.sort(key=lambda x: x['recommended_start'])
    return schedule

def create_google_calendar_link(vaccine_name, start_date):
    """Googleカレンダーへの追加リンクを生成する"""
    base_url = "https://www.google.com/calendar/render?action=TEMPLATE"
    
    # タイトル
    text = quote(f"予防接種: {vaccine_name}")
    
    # 日付 (終日)
    start_date_str = start_date.strftime("%Y%m%d")
    end_date = start_date + timedelta(days=1)
    end_date_str = end_date.strftime("%Y%m%d")
    dates = f"{start_date_str}/{end_date_str}"
    
    # 詳細
    details = quote(f"{vaccine_name}の予防接種を受けましょう。\n病院の予約などを確認してください。")
    
    # 完全なURLを生成
    full_url = f"{base_url}&text={text}&dates={dates}&details={details}"
    
    return f'<a href="{full_url}" target="_blank">📅 Googleカレンダーに追加</a>'


def main():
    st.set_page_config(page_title="ベビワク・リマインダー", page_icon="👶")

    st.title('👶 ベビワク・リマインダー')

    menu = ["ダッシュボード", "お子様情報", "スケジュール一覧", "各ワクチンの情報", "病院検索", "メール通知設定"]
    choice = st.sidebar.selectbox("メニュー", menu)

    if 'children' not in st.session_state:
        st.session_state['children'] = []

    if choice == "ダッシュボード":
        st.subheader("ようこそ！")
        st.write('お子様の予防接種スケジュールを、もっと簡単に、もっと分かりやすく。')

        if not st.session_state.children:
            st.info("まずは「お子様情報」からお子様を登録してください。")
            return
        
        st.write("---")
        
        # 複数のお子様に対応
        selected_child_name = st.selectbox(
            "お子様を選択してください", 
            [child['name'] for child in st.session_state.children]
        )
        selected_child = next((c for c in st.session_state.children if c['name'] == selected_child_name), None)

        if selected_child:
            schedule = selected_child['schedule']
            
            # 次に接種するワクチンを探す
            next_vaccine = next((item for item in schedule if item['status'] == '未接種'), None)
            
            col1, col2 = st.columns(2)
            with col1:
                st.metric("お子様の名前", f"{selected_child['name']} ちゃん")
            with col2:
                if next_vaccine:
                    days_left = (next_vaccine['recommended_start'] - date.today()).days
                    st.metric("次の接種予定日まで", f"あと {days_left} 日", delta=f"{next_vaccine['vaccine_name']}")
                else:
                    st.metric("次の接種予定", "すべて完了！", "🎉")
            
            # スケジュールの進捗
            total_shots = len(schedule)
            completed_shots = sum(1 for item in schedule if item['status'] == '接種済み')
            progress = completed_shots / total_shots if total_shots > 0 else 0
            
            st.write("接種スケジュールの進捗")
            st.progress(progress)
            st.write(f"{completed_shots} / {total_shots} 回 完了")

    elif choice == "お子様情報":
        st.subheader("お子様情報登録")

        with st.form(key='child_form'):
            name = st.text_input("お子様の名前（ニックネーム）")
            birth_date = st.date_input("生年月日",
                                       min_value=date(date.today().year - 10, 1, 1),
                                       max_value=date.today())
            submit_button = st.form_submit_button(label='登録する')

            if submit_button and name:
                schedule = calculate_schedule(birth_date)
                new_child = {'name': name, 'birth_date': birth_date, 'schedule': schedule}
                st.session_state['children'].append(new_child)
                st.success(f"{name}ちゃんを登録しました！")
            elif submit_button:
                st.warning("名前を入力してください。")

        st.write("---")
        st.subheader("登録済みのお子様")
        if st.session_state['children']:
            for i, child in enumerate(st.session_state['children']):
                st.write(f"{i+1}. {child['name']}ちゃん ({child['birth_date']})")
        else:
            st.info("まだお子様が登録されていません。")

    elif choice == "スケジュール一覧":
        st.subheader("予防接種スケジュール")

        if not st.session_state['children']:
            st.warning("まず「お子様情報」からお子様を登録してください。")
            return

        child_names = [child['name'] for child in st.session_state['children']]
        selected_name = st.selectbox("お子様を選択", child_names)

        selected_child = next((child for child in st.session_state['children'] if child['name'] == selected_name), None)

        if selected_child:
            st.write(f"### {selected_child['name']}ちゃんのスケジュール")
            
            schedule_data = selected_child['schedule']
            birth_date = selected_child['birth_date']

            # スケジュールを月齢でグループ化
            grouped_schedule = {}
            for i, item in enumerate(schedule_data):
                r = relativedelta(item['recommended_start'], birth_date)
                month_age = r.years * 12 + r.months
                if month_age not in grouped_schedule:
                    grouped_schedule[month_age] = []
                # 元のインデックスも一緒に保存して、ウィジェットのキーを一意に保つ
                grouped_schedule[month_age].append((item, i))

            # 月齢の昇順で表示
            for month_age in sorted(grouped_schedule.keys()):
                
                # 月齢の見出しを表示
                if month_age == 0:
                    st.subheader(f"🗓️ 生後1ヶ月未満")
                elif month_age < 12:
                    st.subheader(f"🗓️ 生後 {month_age} ヶ月")
                else:
                    years = month_age // 12
                    months = month_age % 12
                    age_str = f"{years}歳"
                    if months > 0:
                        age_str += f" {months}ヶ月"
                    st.subheader(f"🗓️ {age_str}")

                # その月に接種するワクチンのカードを表示
                for item, original_index in grouped_schedule[month_age]:
                    with st.container(border=True):
                        col1, col2 = st.columns([2, 1])

                        with col1:
                            st.markdown(f"**{item['vaccine_name']}**")
                            st.caption(f"推奨期間: {item['recommended_start'].strftime('%Y/%m/%d')} ~ {item['recommended_end'].strftime('%Y/%m/%d')}")

                            unique_key = f"{selected_child['name']}_{original_index}"
                            
                            # 接種記録エリア
                            sub_col1, sub_col2 = st.columns([1, 2])
                            with sub_col1:
                                checked = st.checkbox("接種済み", key=f"check_{unique_key}", value=(item['status'] == '接種済み'))
                            with sub_col2:
                                if checked:
                                    item['status'] = '接種済み'
                                    item['shot_date'] = st.date_input(
                                        "接種日",
                                        value=item.get('shot_date', item['recommended_start']),
                                        key=f"date_{unique_key}",
                                        label_visibility="collapsed"
                                    )
                                else:
                                    item['status'] = '未接種'
                                    if 'shot_date' in item:
                                        del item['shot_date']
                        
                        with col2:
                            # 状況表示
                            is_due = item['recommended_start'] <= date.today() <= item['recommended_end']
                            is_past = date.today() > item['recommended_end'] and item['status'] == '未接種'
                            
                            if item['status'] == '接種済み':
                                st.success("✔️ 接種済み", icon="✔️")
                                if 'shot_date' in item:
                                    st.write(f"接種日: {item['shot_date'].strftime('%Y/%m/%d')}")
                            elif is_due:
                                st.warning("⚠️ 推奨期間", icon="⚠️")
                            elif is_past:
                                st.error("❌ 期間超過", icon="❌")
                            else:
                                st.info("🔜 予定", icon="🔜")

                            # Googleカレンダーへのリンクに変更
                            if item['status'] == '未接種':
                                st.markdown(create_google_calendar_link(item['vaccine_name'], item['recommended_start']), unsafe_allow_html=True)
                    st.write("") # カード間のスペース


    elif choice == "各ワクチンの情報":
        st.subheader("各ワクチンの情報")
        st.write("各ワクチンについての詳細情報を確認できます。")

        # ダミーのワクチン情報
        vaccine_details = {
            "B型肝炎": "B型肝炎ウイルスの感染によって起こる肝臓の病気を防ぎます。すべての子どもに接種が推奨されます。",
            "ロタウイルス": "ロタウイルス胃腸炎による重症化を防ぎます。飲むタイプのワクチンです。",
            "ヒブ": "インフルエンザ菌b型による細菌性髄膜炎などの深刻な病気を予防します。",
            "小児用肺炎球菌": "肺炎球菌による細菌性髄膜炎や肺炎などを予防します。",
            "四種混合(DPT-IPV)": "ジフテリア、百日せき、破傷風、ポリオ（急性灰白髄炎）を予防します。",
            "BCG": "結核、特に子どもの重い結核を予防するためのワクチンです。",
            "MR(麻しん風しん混合)": "麻しん（はしか）と風しんを予防します。2回の接種が必要です。",
            "水痘(みずぼうそう)": "水痘（みずぼうそう）の重症化を防ぎます。",
            "日本脳炎": "日本脳炎ウイルスの感染によって起こる、重い脳の病気を防ぎます。",
        }

        # VACCINESリストからワクチン名を取得してプルダウンメニューを作成
        vaccine_names = sorted(list(set([v['name'] for v in VACCINES])))
        selected_vaccine = st.selectbox("情報を知りたいワクチンを選択してください", vaccine_names)

        if selected_vaccine:
            st.write(f"#### {selected_vaccine}")
            # getメソッドで、キーが存在しない場合のデフォルト値を設定
            st.info(vaccine_details.get(selected_vaccine, "詳細情報が見つかりませんでした。"))
            st.write("（出典: 厚生労働省、国立感染症研究所などの情報を基にしたダミーテキストです）")


    elif choice == "病院検索":
        st.subheader("🏥 病院検索")
        
        # --- APIキーのチェック ---
        try:
            api_key = st.secrets["google_maps_api_key"]
        except (FileNotFoundError, KeyError):
            st.error("APIキーが設定されていません。")
            st.info(
                "管理者向けメッセージ:\n"
                "1. プロジェクトルートに `.streamlit/secrets.toml` ファイルを作成してください。\n"
                "2. そのファイルに `google_maps_api_key = \"YOUR_API_KEY\"` の形式でAPIキーを保存してください。"
            )
            return

        gmaps = googlemaps.Client(key=api_key)

        # 出発地、目的地、移動手段の入力
        col1, col2 = st.columns(2)
        with col1:
            start_address = st.text_input("出発地を入力してください（例：自宅住所）", "東京駅")
        with col2:
            keyword = st.text_input("周辺で検索したい施設", "小児科")

        mode_options_dict = {
            "車": "driving",
            "公共交通機関": "transit",
            "徒歩": "walking"
        }
        selected_mode_japanese = st.selectbox(
            "移動手段を選択",
            options=list(mode_options_dict.keys())
        )
        selected_mode_api = mode_options_dict[selected_mode_japanese]

        search_button = st.button("検索")

        if "hospitals" not in st.session_state:
            st.session_state.hospitals = None

        if search_button:
            try:
                # 住所から緯度経度を取得
                geocode_result = gmaps.geocode(start_address, language='ja')
                if not geocode_result:
                    st.warning("指定された出発地が見つかりませんでした。別のキーワードでお試しください。")
                    return
                
                start_location = geocode_result[0]['geometry']['location']
                start_lat, start_lng = start_location['lat'], start_location['lng']

                # 周辺の小児科を検索
                places_result = gmaps.places_nearby(
                    location=(start_lat, start_lng),
                    radius=2000,  # 半径2km
                    keyword=keyword,
                    language='ja'
                )
                
                st.session_state.hospitals = places_result.get('results', [])
                if not st.session_state.hospitals:
                    st.info("周辺に施設が見つかりませんでした。")

            except Exception as e:
                st.error(f"検索中にエラーが発生しました: {e}")

        # 検索結果の表示
        if st.session_state.hospitals:
            hospitals_data = []
            for place in st.session_state.hospitals:
                hospitals_data.append({
                    'name': place['name'],
                    'lat': place['geometry']['location']['lat'],
                    'lon': place['geometry']['location']['lng'],
                    'address': place.get('vicinity', '住所情報なし'),
                    'rating': place.get('rating', '評価なし'),
                    'website': place.get('website', None),
                    'place_id': place.get('place_id')
                })
            
            df = pd.DataFrame(hospitals_data)
            st.write(f"「{start_address}」周辺の「{keyword}」リスト ({len(df)}件)")
            st.map(df[['lat', 'lon']])

            # Session stateの初期化
            if 'nearby_places' not in st.session_state:
                st.session_state.nearby_places = {}

            for index, row in df.iterrows():
                with st.container(border=True):
                    st.write(f"**{row['name']}**")
                    st.write(f"住所: {row['address']}")
                    st.write(f"評価: {row['rating']} ⭐")

                    # --- Directions APIを呼び出して移動時間を取得 ---
                    try:
                        directions_result = gmaps.directions(
                            start_address,
                            f"place_id:{row['place_id']}",
                            mode=selected_mode_api, # 選択された移動手段を使用
                            language="ja"
                        )
                        if directions_result:
                            duration = directions_result[0]['legs'][0]['duration']['text']
                            distance = directions_result[0]['legs'][0]['distance']['text']
                            
                            # アイコンを選択
                            icon = "🚗"
                            if selected_mode_api == "transit":
                                icon = "🚇"
                            elif selected_mode_api == "walking":
                                icon = "🚶"
                                
                            st.info(f"{icon} {selected_mode_japanese}での所要時間: 約 {duration} ({distance})")
                    except Exception:
                        # ルートが見つからない場合などはエラーになるため、その場合は何も表示しない
                        pass


                    links = []
                    # 緯度・経度を使って、より直接的に地図上の場所を指定する
                    if pd.notna(row['lat']) and pd.notna(row['lon']):
                        maps_url = f"https://www.google.com/maps?q={row['lat']},{row['lon']}"
                        links.append(f'<a href="{maps_url}" target="_blank">Google Mapで開く</a>')
                    
                    if row['website']:
                        links.append(f'<a href="{row["website"]}" target="_blank">公式サイト</a>')

                    if links:
                        st.markdown(" | ".join(links), unsafe_allow_html=True)
                    
                    st.write("---")
                    st.write("**🏥 この施設の周辺を検索:**")
                    
                    # 周辺検索ボタン
                    btn_cols = st.columns(3)
                    place_types = {"カフェ": "cafe", "レストラン": "restaurant", "公園": "park"}
                    icons = {"カフェ": "☕", "レストラン": "🍔", "公園": "🌳"}
                    
                    for place_jp, place_en in place_types.items():
                        unique_btn_key = f"btn_{row['place_id']}_{place_en}"
                        if btn_cols[list(place_types.keys()).index(place_jp)].button(f"{icons[place_jp]} {place_jp}", key=unique_btn_key):
                            
                            # 周辺施設を検索 (基本的な情報のみ)
                            nearby_places_result = gmaps.places_nearby(
                                location=(row['lat'], row['lon']),
                                radius=500,  # 半径500m
                                keyword=place_jp,
                                language='ja'
                            )
                            
                            # 各施設の詳細情報を取得 (websiteなど)
                            detailed_places = []
                            for place in nearby_places_result.get('results', [])[:5]: # 上位5件に絞る
                                try:
                                    place_details = gmaps.place(place_id=place['place_id'], language='ja')
                                    detailed_places.append(place_details['result'])
                                except Exception:
                                    # 詳細が取れない場合はスキップ
                                    continue
                            
                            st.session_state.nearby_places[row['place_id']] = detailed_places
                            st.session_state.last_clicked = f"{row['place_id']}_{place_en}"

                    # 検索結果の表示エリア
                    if row['place_id'] in st.session_state.nearby_places and st.session_state.last_clicked.startswith(row['place_id']):
                        
                        nearby_places_list = st.session_state.nearby_places[row['place_id']]
                        
                        if nearby_places_list:
                            st.write(f"**周辺のスポット:**")
                            for place in nearby_places_list:
                                place_name = place['name']
                                place_rating = place.get('rating', 'なし')
                                website_url = place.get('website')

                                # 緯度経度からGoogle Mapリンクを生成
                                place_lat = place['geometry']['location']['lat']
                                place_lon = place['geometry']['location']['lng']
                                maps_link = f"https://www.google.com/maps?q={place_lat},{place_lon}"
                                
                                # Webサイトがあれば施設名をリンクにし、なければテキストのまま
                                if website_url:
                                    display_name = f"<a href='{website_url}' target='_blank'>{place_name}</a>"
                                else:
                                    display_name = place_name

                                st.markdown(f"- **{display_name}** (評価: {place_rating}) <a href='{maps_link}' target='_blank'>📍</a>", unsafe_allow_html=True)
                        else:
                            st.info("周辺に該当する施設は見つかりませんでした。")
                st.write("") # コンテナ間のスペース


    elif choice == "メール通知設定":
        st.subheader("設定") # タイトルを元に戻す

        st.write("#### 通知設定")
        
        if 'notification_enabled' not in st.session_state:
            st.session_state.notification_enabled = True
        if 'notification_email' not in st.session_state:
            st.session_state.notification_email = "example@email.com"

        st.session_state.notification_enabled = st.checkbox(
            "接種日が近づいたらメールで通知する", 
            value=st.session_state.notification_enabled
        )
        
        if st.session_state.notification_enabled:
            st.session_state.notification_email = st.text_input(
                "通知先メールアドレス",
                value=st.session_state.notification_email
            )

            if st.button("テスト通知を送信"):
                if st.session_state.notification_email:
                    st.success(f"「{st.session_state.notification_email}」にテスト通知を送信しました。(実際には送信されません)")
                else:
                    st.warning("メールアドレスを入力してください。")
        
        st.write("---")

if __name__ == '__main__':
    main()

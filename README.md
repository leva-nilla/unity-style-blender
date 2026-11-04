# Unity View Controls

[日本語](#ja) | [English](#en)

[Download v0.1.9 / ダウンロード](https://github.com/leva-nilla/unity-style-blender/releases/download/v0.1.9/unity_view_controls-0.1.9.zip) · [Releases](https://github.com/leva-nilla/unity-style-blender/releases)

<a id="ja"></a>

## 日本語

Blenderの3Dビュー操作をUnity Editorに寄せるアドオン。Blender 4.4以降が対象で、Windows / Blender 4.4.3で検証しています。外部Pythonライブラリは不要です。アドオンの設定ラベルは現在日本語です。

### 操作

- Alt + 左ドラッグで周回、中ドラッグで平行移動、Alt + 右ドラッグでズーム。
- 透視投影では右ボタンを押している間に視点回転とWASD移動、Q/E下降・上昇。Shiftで加速、ホイールで速度調整。
- 平行投影はQEADで画面内をパン、W/Sで拡大・縮小。Nメニューから「WASDでパン・Q/Eでズーム」に変更できます。
- 移動座標はNメニューで「視点基準／ワールド基準」を切り替えます。視点基準では画面の右・上・奥、ワールド基準では水平移動とZ方向の上下を使います。平行投影のワールド基準は画面に近い世界座標の2軸に沿ってパンします。
- 右ボタン保持中にCtrlを押すと微速移動します。移動は加減速を含めて時間ベースで計算し、初期設定では120Hzで更新を要求します。
- オブジェクトモードでW/E/Rの移動・回転・拡縮ツール切替、Fで選択物へフォーカス。
- アウトライナーでコレクションやオブジェクトの三角をAlt＋クリックすると、子孫の階層までまとめて開閉します。通常クリックやBlender標準のShift＋クリックも使えます。
- コレクションや親オブジェクトを選び、右クリックメニューの「子をすべて展開／子をすべて折りたたみ」で、アクティブな項目の配下を一括開閉できます。複数選択でも、対象はアクティブな一つです。
- 右クリックだけなら、現在のモードのコンテキストメニューを開きます。
- 移動後に右ボタンを離すと確定。Escやウィンドウの非アクティブ化で開始時の視点へ戻します。
- 無効化で追加したキー設定と実行中の操作を解除。既存キーマップの編集・削除、作品の編集、プリファレンスの自動保存は行いません。

視点操作は以下の22モードに対応します。追加した編集・ペイント系モードでは右ボタンの割り当てを追加し、Alt＋クリックによるボーン選択などの専用操作を保持します。テクスチャペイントは3Dビューが対象です。

### モード対応

| モード | 視点移動 | 短い右クリック |
| --- | --- | --- |
| オブジェクト・メッシュ編集・ポーズ | 対応 | 標準メニュー |
| スカルプト・頂点ペイント・ウェイトペイント・テクスチャペイント | 対応 | 標準ブラシ設定 |
| ボーン・カーブ・ヘアカーブ・サーフェス・テキスト・メタボール・ラティス編集 | 対応 | 標準メニュー |
| ポイントクラウド編集・ヘアカーブのスカルプト | 対応 | 標準の右クリックUIなし |
| パーティクル編集 | 対応 | 標準メニュー |
| Grease Pencil編集 | 対応 | 標準メニュー |
| Grease Pencil描画・スカルプト・ウェイトペイント・頂点ペイント | 対応 | 標準ブラシ設定 |

Blender 4.4.3で確認しています。APIに残っている旧Grease Pencilの互換用モード識別子は対象外です。導入済みBlenderのモード識別子との照合結果は `tests/check_mode_coverage.py` で再生成できます。

### 編集ギズモ・プロポーショナル編集

編集モードで「N → View → Unity View Controls」の「移動・回転・拡縮」を選ぶと、Blender標準の軸ギズモを使えます。頂点・制御点などを選択してから軸をドラッグしてください。メッシュ、ボーン、カーブ、ヘアカーブ、サーフェス、メタボール、ラティス、Grease Pencilの編集が対象です。テキスト・ポイントクラウド編集にはギズモ切替ボタンを追加しません。

同じ場所にギズモ座標と、プロポーショナル編集のオン／オフ、影響半径、減衰、接続のみ、投影を配置しています。Blender標準の設定を共有するため、Oキーやヘッダーでの切替とも連動します。影響範囲は変形中のホイールでも調整できます。ボーン編集では標準のプロポーショナル編集が使えないため、この設定を表示しません。

「編集モードでW/E/Rを使用」をオンにすると、W＝移動、E＝回転、R＝拡縮へ切り替えられます。初期値はオフです。オンの間はEの押し出しやRの回転などがギズモ切替へ置き換わります。オフのままでもNメニューのボタンでギズモを選べます。

Nメニューとアドオン設定の「押し出しの代替キー」で、A〜Z・F1〜F12とShift/Ctrl/Altを組み合わせて選べます。初期値はShift＋Eです。代替キーは編集W/E/Rがオンの間だけ有効で、「割当なし」も選べます。修飾キーのないW/E/Rはギズモと重なるため割り当てません。現在のモードの標準・ユーザー設定キーと競合する場合は、その操作名を表示します。独自アドオンのモーダル入力など、すべての競合を検出するものではありません。

Shift＋Eはメッシュのクリースとボーンの分岐押し出しを置き換えます。標準操作を残す場合は別の組み合わせか「割当なし」を選んでください。編集W/E/Rをオフにすると追加したキーだけを取り除き、元のキー設定を使います。既存キーマップは編集・保存しません。

Nメニューの「押し出し」ボタンは、編集W/E/Rのオン・オフにかかわらず使えます。メッシュ、ボーン、カーブ、ヘアカーブ、サーフェス、Grease Pencilで、そのモードの標準押し出しを開始します。確定・キャンセル・Undoも標準操作に従います。メタボールとラティスには標準の押し出しがないため、ボタンと代替キーを追加しません。

「影響範囲を表示」がオンなら、プロポーショナル編集をオンにして点を選ぶと、ビューポートにオレンジ色の円を表示します。Nメニューの影響半径を変えると即座に大きさが変わり、選択位置・パン・ズームにも追従します。円は選択点の中心から半径を示す目安です。複数点の選択、接続のみ、投影、隠れた要素などによる実際の影響領域を示すものではありません。

表示はメッシュ、カーブ、ヘアカーブ、サーフェス、メタボール、ラティス、Grease Pencilの編集が対象です。選択なし・プロポーショナル編集オフ・編集モード終了・ビューポートのオーバーレイ非表示では円を隠します。変形中はBlender標準の範囲表示に切り替えます。プレビューは形状・選択・Undo履歴を変更しません。

### インストール

1. [Release v0.1.9](https://github.com/leva-nilla/unity-style-blender/releases/tag/v0.1.9)から `unity_view_controls-0.1.9.zip` をダウンロードします。自動生成の「Source code」ZIPとは別のファイルです。
2. Blenderで「編集 → プリファレンス → エクステンションを入手」を開きます。
3. 右上のメニューの「ディスクからインストール」でZIPを指定し、有効化します。
4. 「アドオン」でUnity View Controlsを開くと、「操作」と「フライスルー」の設定が表示されます。

一括開閉は、アウトライナーのツリー表示だけを操作します。所属、親子関係、表示・非表示、ビューレイヤーからの除外は変更しません。展開状態が混在する階層のAlt＋クリックは、まずすべて展開し、もう一度で折りたたみます。

### コンフィグ

「編集 → プリファレンス → アドオン → Unity View Controls」から変更します。フライスルーの値は、次に右ボタン操作を始めたときに適用されます。保存はBlenderのプリファレンス自動保存、または「プリファレンスを保存」を使います。

3DビューでNキーを押し、「View（ビュー）→ Unity View Controls」からも速度・感度・移動座標・平行投影の操作・FOV補正・滑らかさを調整できます。「詳細設定」を開くとShift/Ctrl倍率、ホイール倍率、更新頻度、上下反転も表示されます。アドオン設定と同じ値を共有します。

Nメニューの「FOV（長辺）」は、操作中のビューポートの長辺方向の画角を度で調整します。即座に反映されます。平行投影とカメラビューでは無効で、実カメラは変更しません。通常のViewパネルの焦点距離とも連動します。

| 設定 | 初期値 | 調整内容 |
| --- | --- | --- |
| 操作の切替 | 編集W/E/Rのみオフ | 視点操作、オブジェクトW/E/R・F、編集W/E/R、階層一括開閉を個別に切替 |
| 移動速度 | 5 | 通常の移動速度 |
| ホイール調整した速度を記憶 | オン | 調整後の速度を共有設定に反映し、次回の操作にも引き継ぐ。保存は通常のプリファレンス保存に従う |
| 見回し感度 | 3.500 | 倍率0.002〜100。小さいほど低感度。ドラッグは0.01刻み、Shiftドラッグで微調整 |
| 移動座標 | 視点基準 | ワールド基準へ切替可能。切替はNメニューから行う |
| 平行投影のキー配置 | QEADでパン・W/Sでズーム | WASDでパン・Q/Eでズームへ切替可能 |
| 平行投影ズーム倍率 | 3 | 拡大・縮小の速さ |
| FOV感度補正 | 0 | 0は補正なし。1では50mmより長い焦点距離に応じて見回し感度を下げる。平行投影には適用しない |
| Shiftの速度倍率 | 4 | 加速倍率 |
| Ctrlの微速倍率 | 0.25 | 精密な移動の倍率 |
| ホイールの速度倍率 | 1.2 | 1段ごとの速度変化 |
| 更新頻度 | 120Hz | 30〜240Hz。移動更新の要求頻度 |
| 移動の滑らかさ | 0.060秒 | 加減速の応答時間。大きいほどゆっくり速度が変わり、0で即応 |
| 見回しの上下を反転 | オフ | マウスの縦方向を反転 |
| 押し出しの代替キー | Shift＋E | 編集W/E/Rオン時だけ有効。キーと修飾キーを設定可能 |
| 影響範囲を表示 | オン | 対応する編集モードでプロポーショナル編集の半径を表示 |

DPI1600でのユーザーの調整値をもとに、新規導入時の初期感度を3.500にしています。既存の保存済み感度は維持され、旧初期値は新しい倍率表示で6.000になります。値を直接入力すると、ドラッグの刻みより細かく指定することもできます。

更新頻度は描画FPSの保証ではありません。シーンや描画処理が重い場合、設定値より更新が遅れることがあります。加減速は経過時間から計算し、更新頻度を変えても移動速度と応答が変わらないようにしています。キーを離した後の減速は、右ボタンを保持している間だけ続きます。右ボタンを離すとその場で確定します。

アドオンを無効化すると、追加した操作は解除されます。Blender標準キーマップ、左クリック選択、3ボタンマウスを基準としています。独自キーマップや入力系アドオンとの組み合わせは未検証です。

### Unityとの違い

- Blenderの座標系（Zが上）を維持します。透視投影のワールド基準ではQは下降、Eは上昇です。
- UnityのQハンドツール、TのRectツール、Yの複合ツール、追従フォーカス、スナップ設定は今回の範囲外です。
- カメラビューや回転ロック中は右ボタン飛行を開始しません。カメラビューを抜けるか、回転ロックを解除してください。
- フライスルーは開始時の投影方式を維持します。平行投影ではWASD移動・見回し中も平行投影のままで、右ボタンを離しても透視投影へ切り替わりません。Escでは開始時の位置・向き・表示範囲を復元します。
- マウス周回・平行移動・ズームはBlenderの標準処理を使います。速度や慣性までUnityと完全に一致させるものではありません。
- 速度の記憶がオンなら、ホイール調整した値を移動速度として引き継ぎます。オフではその操作中だけ有効です。Escは視点を戻しますが、記憶した速度設定は維持します。

<a id="development-commands"></a>

### 開発・確認

ソースは [v0.1.9タグ](https://github.com/leva-nilla/unity-style-blender/tree/v0.1.9)にあります。ソースを取得する場合は、このタグをチェックアウトしてください。

```powershell
git clone https://github.com/leva-nilla/unity-style-blender.git
cd unity-style-blender
git checkout v0.1.9
```

以下はPowerShellで、プロジェクトのルートから実行します。

```powershell
.\scripts\build.ps1
& 'C:\Program Files (x86)\Steam\steamapps\common\Blender\blender.exe' `
  --background --factory-startup --python-exit-code 1 --python tests/test_motion.py
& 'C:\Program Files (x86)\Steam\steamapps\common\Blender\blender.exe' `
  --background --factory-startup --python-exit-code 1 --python tests/check_mode_coverage.py
& 'C:\Program Files (x86)\Steam\steamapps\common\Blender\blender.exe' `
  --factory-startup --enable-event-simulate --python tests/run_blender_tests.py
& 'C:\Program Files (x86)\Steam\steamapps\common\Blender\blender.exe' `
  --factory-startup --enable-event-simulate --python tests/run_outliner_tests.py
& 'C:\Program Files (x86)\Steam\steamapps\common\Blender\blender.exe' `
  --factory-startup --enable-event-simulate --python tests/run_extended_tests.py
& 'C:\Program Files (x86)\Steam\steamapps\common\Blender\blender.exe' `
  --factory-startup --enable-event-simulate --python tests/run_editing_config_tests.py
```

ビルドはBlenderの公式エクステンション検証とZIP生成を行います。テストは初期状態の別ウィンドウを使い、実際のキーディスパッチ、飛行、キャンセル、登録・解除、既存キー保持を検証します。アウトライナーテストは専用の入れ子コレクションで再帰開閉と所属・表示設定の保持を確認します。`artifacts/test-results.json` と `artifacts/outliner-results.json` に結果を出し、目視確認用にウィンドウを残します。追加モードのテストは15モードの入力・データ保持、軸ギズモの実ドラッグ、プロポーショナル変形とUndo、編集W/E/Rを検証します。結果は `artifacts/extended-results.json`、専用の確認シーンは `artifacts/gizmo017.blend` に保存します。代替キーと半径プレビューのテストは、6つの編集モードの実キー入力と押し出し・Undo、Nメニューのコンテキスト、競合検出、半径表示の追従と後片付けを確認し、`artifacts/editing-config-results.json` に保存します。通常の作品やユーザー設定は保存しません。

### 参照仕様

- [Unity 2022.3 Scene view navigation](https://docs.unity3d.com/2022.3/Documentation/Manual/SceneViewNavigation.html)
- [Blender KeyMaps API](https://docs.blender.org/api/4.4/bpy.types.KeyMaps.html)
- [Blender 4.4.3のビューポート投影計算](https://github.com/blender/blender/blob/v4.4.3/source/blender/blenkernel/intern/camera.cc)

独立したアドオンとして実装します。座標系とオブジェクト構造を維持し、変形にはBlender標準のツールを使います。

### ライセンス

[GNU GPL v3.0以降](https://github.com/leva-nilla/unity-style-blender/blob/v0.1.9/addon/LICENSE)。

<a id="en"></a>

## English

Unity-style 3D View controls for Blender. Tested on Windows with Blender 4.4.3; the extension requires Blender 4.4 or later. No external Python libraries are needed. The add-on settings currently use Japanese labels.

### Installation

1. Download `unity_view_controls-0.1.9.zip` from [Release v0.1.9](https://github.com/leva-nilla/unity-style-blender/releases/tag/v0.1.9). Choose the extension ZIP, separately from GitHub's automatically generated source archives.
2. In Blender, open **Edit → Preferences → Get Extensions**.
3. Open the menu in the upper-right corner, choose **Install from Disk**, select the ZIP, and enable the extension.
4. Open **Add-ons → Unity View Controls** for preferences, or press **N** in the 3D View and choose **View → Unity View Controls**.

### Controls

| Input | Action |
| --- | --- |
| Alt + left drag | Orbit |
| Middle drag | Pan |
| Alt + right drag | Zoom |
| Hold right mouse + WASD | Move through a perspective view |
| Q / E while holding right mouse | Move down / up in a perspective view |
| Shift / Ctrl while holding right mouse | Boost / precision movement |
| Mouse wheel while holding right mouse | Adjust movement speed |
| Short right click | Open the mode's native context menu or brush settings, when available |
| Release right mouse | Confirm navigation |
| Esc or window deactivation | Restore the starting view |
| W / E / R in Object Mode | Select Move / Rotate / Scale gizmos |
| F in Object Mode | Frame the selection |

In orthographic views, the default layout uses **QEAD to pan and W/S to zoom**. The N-panel can switch this to **WASD to pan and Q/E to zoom**. Navigation preserves the original projection, including after releasing right mouse. Esc restores the starting position, rotation, and view distance.

Choose **View** or **World** movement coordinates in the N-panel. View coordinates follow the screen's right, up, and depth axes. World coordinates use horizontal movement and Blender's Z axis for height. Orthographic world-space panning uses the two world axes closest to the view plane.

Movement uses elapsed-time integration, including acceleration and deceleration. The default update request rate is 120 Hz. Deceleration continues after releasing a movement key while right mouse remains held; releasing right mouse confirms the current view immediately.

### Collection and object hierarchies

- Alt-click a disclosure triangle in the Outliner to recursively expand or collapse a collection or object hierarchy. Normal clicking and Blender's native Shift-click remain available.
- The collection and object context menus also provide **子をすべて展開 / 子をすべて折りたたみ** (expand / collapse all children).
- With multiple items selected, the menu acts on the active item only. For mixed expansion states, Alt-click expands the whole subtree first; the next Alt-click collapses it.

These actions only change the Outliner tree display. They preserve collection membership, parenting, visibility, and view-layer exclusion.

### Supported modes

Navigation supports these 22 current Blender modes:

| Modes | Navigation | Short right click |
| --- | --- | --- |
| Object, Mesh Edit, Pose | Supported | Native menu |
| Sculpt, Vertex Paint, Weight Paint, Texture Paint | Supported | Native brush settings |
| Armature, Curve, Hair Curves, Surface, Text, Metaball, Lattice Edit | Supported | Native menu |
| Point Cloud Edit, Hair Curves Sculpt | Supported | No native right-click UI |
| Particle Edit | Supported | Native menu |
| Grease Pencil Edit | Supported | Native menu |
| Grease Pencil Draw, Sculpt, Weight Paint, Vertex Paint | Supported | Native brush settings |

Texture Paint support applies to the 3D View. No bindings are installed in the 2D Image Editor. Additional edit and paint mode bindings are limited to right mouse, preserving mode-specific chords such as Alt-click bone selection.

Tested with Blender 4.4.3. Legacy Grease Pencil compatibility identifiers still exposed by the API are excluded. Run `tests/check_mode_coverage.py` to compare the supported set against the installed Blender's mode identifiers.

### Edit gizmos and extrusion

In a supported Edit Mode, select vertices or control points, then choose **移動 / 回転 / 拡縮** (Move / Rotate / Scale) in **N → View → Unity View Controls** and drag a native gizmo axis. Gizmos are provided for Mesh, Armature, Curve, Hair Curves, Surface, Metaball, Lattice, and Grease Pencil editing. Text and Point Cloud editing receive navigation support without these gizmo buttons.

**編集モードでW/E/Rを使用** enables W/E/R gizmo switching in Edit Mode. It is **off by default**, preserving native modeling shortcuts. When enabled, E extrusion and R rotation are replaced by gizmo switching. The N-panel gizmo buttons also work with this option off.

Configure an alternative extrusion shortcut in the N-panel or add-on preferences: choose **A–Z or F1–F12**, with any combination of **Shift/Ctrl/Alt**, or choose no assignment. The default is **Shift+E**. This shortcut is active only while Edit Mode W/E/R is enabled. Bare W/E/R cannot be assigned because they are reserved for gizmo switching.

Conflicting native or user-defined shortcuts are listed by operation name. The default Shift+E replaces **edge crease in Mesh Edit Mode** and **forked extrusion in Armature Edit Mode**. Select another combination or no assignment to keep those operations on their original keys. Turning Edit Mode W/E/R off removes the added shortcuts; existing keymaps are never edited or saved. Conflict detection covers the inspected keymaps, including general viewport and window bindings; other add-ons' modal input is outside its scope.

The N-panel **押し出し** (Extrude) button works whether Edit Mode W/E/R is enabled or disabled. It starts the mode's native extrusion in Mesh, Armature, Curve, Hair Curves, Surface, or Grease Pencil editing, with native confirmation, cancellation, and Undo. Metaball and Lattice editing have no native extrusion, so no extrusion button or alternative shortcut is added there.

### Proportional editing and radius preview

The N-panel exposes the native transform orientation, proportional editing toggle, radius, falloff, Connected Only, and Projected settings. These share Blender's settings with the header and O shortcut. The mouse wheel also adjusts the radius during a native transform. Armature Edit Mode has no native proportional editing, so these controls are hidden there.

Enable **影響範囲を表示** (Show influence radius), enable proportional editing, and select control points to see an orange circle in the viewport. The circle responds immediately to N-panel radius changes and follows the selection, panning, and zooming. It shows a radius guide centered on the selected points. Multiple selections, connected/projected options, and hidden elements can produce a different actual influence region.

The preview supports Mesh, Curve, Hair Curves, Surface, Metaball, Lattice, and Grease Pencil editing. It hides with no selection, proportional editing off, Edit Mode exited, or viewport overlays disabled. During native transforms, Blender's native radius display takes over. The preview preserves geometry, selection, and Undo history.

### Configuration

Use **Edit → Preferences → Add-ons → Unity View Controls**, or **N → View → Unity View Controls**. Navigation settings take effect the next time right-mouse navigation starts. Save settings through Blender's preference autosave or **Save Preferences**.

The N-panel shares the same preferences for speed, speed memory, look sensitivity, smoothing, movement coordinates, orthographic keys and zoom speed, and FOV compensation. Expand **詳細設定** (Advanced settings) for Shift/Ctrl multipliers, wheel scaling, update rate, and vertical look inversion.

**FOV（長辺）** adjusts the active viewport's long-axis field of view in degrees and updates immediately. It follows Blender's native viewport focal length. It is disabled in orthographic and camera views and preserves actual camera settings.

| Setting | Default | Behavior |
| --- | --- | --- |
| Feature toggles | All on except Edit Mode W/E/R | Separate navigation, Object Mode W/E/R and F, Edit Mode W/E/R, and hierarchy controls |
| Movement speed | 5 | Normal movement speed |
| Remember wheel-adjusted speed | On | Share the adjusted speed with future navigation sessions; persistence follows preference saving |
| Look sensitivity | 3.500 | Multiplier from 0.002 to 100; drag in 0.01 steps, Shift-drag for finer changes |
| Movement coordinates | View | Switch to World in the N-panel |
| Orthographic layout | QEAD pan, W/S zoom | Optional WASD pan, Q/E zoom |
| Orthographic zoom multiplier | 3 | Zoom speed |
| FOV sensitivity compensation | 0 | 0 disables compensation; 1 reduces sensitivity at focal lengths longer than 50 mm; perspective views only |
| Shift boost | 4 | Movement multiplier |
| Ctrl precision | 0.25 | Fine movement multiplier |
| Wheel speed factor | 1.2 | Speed scaling per wheel step |
| Update rate | 120 Hz | Request rate from 30 to 240 Hz |
| Movement smoothing | 0.060 s | Acceleration/deceleration response time; 0 gives immediate response |
| Invert vertical look | Off | Reverse the vertical mouse direction |
| Alternative extrusion shortcut | Shift+E | Configurable; active only with Edit Mode W/E/R enabled |
| Show influence radius | On | Read-only proportional radius guide in supported Edit Modes |

The default sensitivity 3.500 reflects the user's preferred setting at 1600 DPI. Previously saved sensitivities are preserved; the older default appears as 6.000 on the multiplier scale. Direct numeric entry supports finer values than dragging.

The update rate is a request, not a drawing-FPS guarantee. Heavy scenes can update more slowly. Elapsed-time integration keeps movement speed and smoothing response consistent across update rates.

Disabling the add-on removes its added inputs and cancels active navigation. It preserves existing keymaps, edits, and user preferences. Blender's default keymap, left-click selection, and a three-button mouse are the tested baseline. Custom keymaps and other input add-ons are untested.

### Differences from Unity

- Blender's Z-up coordinates are retained. In perspective World movement, Q moves down and E moves up.
- Unity's Q Hand tool, T Rect tool, Y combined tool, follow-focus behavior, and unified snapping are outside the scope.
- Right-mouse navigation does not start in Camera View or when view rotation is locked. Leave Camera View or unlock rotation first.
- Orbit, pan, and mouse-drag zoom use Blender's native operations. Their speed and inertia are not guaranteed to match Unity exactly.
- With speed memory enabled, wheel changes persist across navigation sessions. Esc restores the view while keeping the remembered speed. Disable speed memory to keep changes within the current navigation session.

### Development and verification

The complete release source is available at [tag v0.1.9](https://github.com/leva-nilla/unity-style-blender/tree/v0.1.9). To work from that source:

```powershell
git clone https://github.com/leva-nilla/unity-style-blender.git
cd unity-style-blender
git checkout v0.1.9
```

Run the PowerShell commands in the [Japanese development section](#development-commands) from the project root. `scripts/build.ps1` uses Blender's official extension validation and ZIP builder. Adjust the Blender executable path for your installation.

GUI checks use isolated factory-startup windows and exercise actual key dispatch, navigation/cancellation, registration/unregistration, and preservation of existing keys and scene data. Outliner checks cover recursive hierarchy actions. Extended mode checks cover 15 added modes, actual gizmo dragging, proportional deformation, and native Undo. Editing-configuration checks cover six extrusion modes, configurable shortcuts, conflicts, N-panel context, radius updates, and cleanup.

Results are written to `artifacts/test-results.json`, `artifacts/outliner-results.json`, `artifacts/extended-results.json`, and `artifacts/editing-config-results.json`. Isolated inspection scenes include `artifacts/gizmo017.blend`. The tests leave inspection windows open and preserve normal user scenes and preferences. Build output, profiles, and test artifacts are excluded from Git.

### References

- [Unity 2022.3 Scene view navigation](https://docs.unity3d.com/2022.3/Documentation/Manual/SceneViewNavigation.html)
- [Blender KeyMaps API](https://docs.blender.org/api/4.4/bpy.types.KeyMaps.html)
- [Blender 4.4.3 viewport projection implementation](https://github.com/blender/blender/blob/v4.4.3/source/blender/blenkernel/intern/camera.cc)

This is an independent add-on. It preserves Blender's coordinate system and object structure and uses Blender's native transformation tools.

### License

[GNU GPL v3.0 or later](https://github.com/leva-nilla/unity-style-blender/blob/v0.1.9/addon/LICENSE).

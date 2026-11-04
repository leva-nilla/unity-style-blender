# Unity View Controls

Blenderの3Dビュー操作をUnity Editorに寄せるアドオン。Windows / Blender 4.4.3を最初の検証対象とします。

## 最初の完成条件

- Alt + 左ドラッグで周回、中ドラッグで平行移動、Alt + 右ドラッグでズーム。
- 右ボタンを押している間に視点回転とWASD移動、Q/E下降・上昇。Shiftで加速、ホイールで速度調整。
- オブジェクトモードでW/E/Rの移動・回転・拡縮ツール切替、Fで選択物へフォーカス。
- 無効化で追加したキー設定と実行中の操作を解除。既存キー設定・作品・起動設定を書き換えない。

## 参照仕様

- [Unity 2022.3 Scene view navigation](https://docs.unity3d.com/2022.3/Documentation/Manual/SceneViewNavigation.html)
- [Blender KeyMaps API](https://docs.blender.org/api/4.4/bpy.types.KeyMaps.html)

独立したアドオンとして実装します。座標系、オブジェクト構造、モデリング機能そのものの変更は対象外です。

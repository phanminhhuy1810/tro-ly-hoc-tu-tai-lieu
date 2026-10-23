import { Mascot, type Coat, type Mood, type Pose } from './Mascot';

// A row of Byte's classmates for the Cộng đồng pages: ginger, grey and cocoa
// cats reading, sipping, typing, waving and napping. Each can be petted.
const CATS: { coat: Coat; glasses: boolean; pose?: Pose; mood?: Mood }[] = [
  { coat: 'grey', glasses: false, pose: 'book' },
  { coat: 'cocoa', glasses: false, mood: 'happy' },
  { coat: 'ginger', glasses: true, pose: 'laptop' },
  { coat: 'grey', glasses: false, pose: 'mug' },
  { coat: 'cocoa', glasses: false, mood: 'wink' },
  { coat: 'ginger', glasses: false, pose: 'flag' },
  { coat: 'grey', glasses: false, pose: 'sleep' },
];

export function CatParade() {
  return (
    <div className="cat-parade" aria-hidden="true">
      {CATS.map((cat, i) => (
        <Mascot key={i} {...cat} size={86} pettable />
      ))}
    </div>
  );
}

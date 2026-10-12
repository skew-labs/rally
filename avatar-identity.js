// Keep ordering and identity hashing in sync with Android AvatarIdentity.kt.
// Immutable IDs select a face; changing a display name never changes it.
export const avatarCharacters=Object.freeze(['v1','mint-v1','coral-v1','blue-v1','gold-v1','rose-v1']);
const editorialFaces=Object.freeze({
 rally:0,
 ce835f7aadde4129bfe8d993385c21d2:1,
 '1a4c47df1581408e913ca68056d07fe7':2,
 c0d47e94549f4e5c93c9e0eacce45c25:4
});
export function avatarIndex(identity,namespace='profile'){
 const key=String(identity||'guest');
 if(namespace==='profile'&&Object.hasOwn(editorialFaces,key))return editorialFaces[key];
 const seed=namespace+':'+key;let hash=0;
 for(let i=0;i<seed.length;i++)hash=(Math.imul(hash,31)+seed.charCodeAt(i))|0;
 return (hash&0x7fffffff)%avatarCharacters.length;
}
export const avatarAsset=(identity,namespace='profile')=>'/assets/rally-character-'+avatarCharacters[avatarIndex(identity,namespace)]+'.webp';
export const profileAvatarAsset=profile=>avatarAsset(profile?.id||profile?.handle);

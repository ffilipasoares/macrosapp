# Siri and the share sheet

Two Apple Shortcuts connect your iPhone to the app. Both use the addresses and
the private key shown in the app under **Settings → Siri and the share sheet**.
Anyone with the key can add to your list, so don't share the Shortcuts with the
key inside.

These steps were written from the API, not yet tried on a phone; the action
names may differ slightly between iOS versions.

## "Add to groceries" (Siri)

In the Shortcuts app, create a shortcut named **Add to groceries** with these actions:

1. **Ask for Input** – type *Text*, prompt "What should I add?"
2. **Get Contents of URL**
   - URL: the *Add to groceries* address from Settings
   - Method: **POST**
   - Headers: `Authorization` = `Bearer YOUR_KEY`
   - Request Body: **JSON**, with one field `item` (Text) set to *Provided Input*
3. **Get Dictionary Value** – get the value for `message` from *Contents of URL*
4. **Speak Text** (or **Show Result**) – *Dictionary Value*

Say **"Hey Siri, add to groceries"**, then the item. You can say several:
"milk, eggs and bread". Siri answers "Added milk, eggs, bread to your
groceries", or tells you it is already on the list.

## "Save recipe" (share sheet)

Create a shortcut named **Save recipe**:

1. In the shortcut's details, turn on **Show in Share Sheet** and limit the
   accepted types to **Images**.
2. **Get Contents of URL**
   - URL: the *Save a recipe screenshot* address from Settings
   - Method: **POST**
   - Headers: `Authorization` = `Bearer YOUR_KEY`
   - Request Body: **Form**, with one field `file` of type *File* set to *Shortcut Input*
3. **Get Dictionary Value** – `message`
4. **Show Notification** – *Dictionary Value*

Take a screenshot of a recipe (in TikTok, Instagram, anywhere), tap Share →
**Save recipe**. The recipe appears in the app marked "check this" so you can
confirm the amounts.

Images up to 8 MB in JPEG, PNG, WebP or HEIC are accepted.

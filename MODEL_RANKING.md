# Modellvalg — konfigurerbar veiledning for teamet

Dette er teamets standard. Hver person setter sin egen rangering med `/start-here`: intervjuet finner modellene maskinen faktisk tilbyr, personen rangerer dem per jobb og velger et review-par, og svaret lagres i `~/.config/patstack/preferences.json`. Den filen går foran denne tabellen for den personen. Tabellen er det dokumenterte standardeksemplet, ikke en måling av kvalitet eller en regel om hvem som får arbeide på en ticket. Bruk modellene og verktøyene som den aktuelle kjøringen faktisk tilbyr.

## Velg etter arbeidet

| Behov | Standardeksempel | Hva må verifiseres? |
|---|---|---|
| Helhetsansvar, koordinering og integrasjon | Opus 5.5 | Tilstrekkelig kontekst, faktisk prosjekttilgang og nødvendige verktøy |
| Frontend-design eller backend-arkitektur | Opus 5.5 | Tilgjengelig modell, relevant erfaring og egnethet for prosjektet |
| Implementering, integrasjoner, tester eller analyse | Sol 6.1 | Faktisk modellidentitet, kjøremiljø og avtalt oppgaveomfang |
| Interaktiv UI-verifisering | Astra i et kjøremiljø som faktisk tilbyr Computer Use | Reell verktøytilgang og testet vert; modellnavnet gir ingen verktøytilgang |
| R2 uavhengig gjennomgang | En fersk reviewer fra motsatt modellfamilie; med bare én leverandør en fersk økt av den under en [reviewer-linse](skills/review/references/lenses.md) | Uavhengighet og påkrevd dybde; manglende obligatorisk gjennomgang rapporteres |
| R3 Council | Ferske vurderinger fra de to konfigurerte modellfamiliene (standard: Opus og Sol), eller med én leverandør to økter under hver sin linse | Uavhengige førstevurderinger, deretter kryssprøving basert på bevis |

## Veiledning ved tildeling

1. Kontroller den levende modellkatalogen på den aktuelle verten. Ikke anta at et alias betyr det samme overalt.
2. Behold faktisk leverandør, modell og kjøremiljø i delegeringsbriefen. Et rollenavn gir verken en modell eller verktøy.
3. Velg kvalitet og egnethet først. Hvis en ønsket eller nødvendig kapasitet mangler, rapporter gapet; ikke gi en annen modell falsk identitet eller senk gjennomgangsnivået i stillhet.
4. Oppstart av en agent gir ingen ny rett til push, merge, deploy, dataendringer eller eksterne meldinger.

Endrede preferanser opphever ingen menneskelige godkjenningsporter, sikkerhetskrav eller krav til uavhengig gjennomgang. Ingen av preferansene begrenser hvilken modell som kan overta en ticket. Den personlige filen er det private, daterte preferansedokumentet; `scripts/preferences.py show` viser den.

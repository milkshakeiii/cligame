using System.Collections;
using System.Collections.Generic;
using System.Linq;
using UnityEngine;

public class ActionsQueue : MonoBehaviour
{
    public GameDisplayer gameDisplayer;

    private List<string> actions = new();
    private string myShipUuid;

    private void OnEnable()
    {
        //ServerPinger.OnZoneStateReceived += ZoneStateReceived;
        ServerPinger.OnNewShipUuidReceived += NewShipUuidReceived;
    }

    private void OnDisable()
    {
        //ServerPinger.OnZoneStateReceived -= ZoneStateReceived;
        ServerPinger.OnNewShipUuidReceived -= NewShipUuidReceived;
    }

    private void NewShipUuidReceived(string myShipUuid)
    {
        this.myShipUuid = myShipUuid;
    }

    // Start is called before the first frame update
    void Start()
    {
        
    }

    // Update is called once per frame
    void Update()
    {
        // when the mouse is clicked
        if (Input.GetMouseButtonDown(0) || Input.GetMouseButtonUp(0))
        {
            // get the world position of the mouse
            Vector3 mousePos = Camera.main.ScreenToWorldPoint(Input.mousePosition);
            mousePos.z = 0;
            Vector2Int boardPosition = new Vector2Int(Mathf.RoundToInt(mousePos.x), Mathf.RoundToInt(mousePos.y));
            if (Input.GetMouseButtonDown(0))
            {
                MouseDown(boardPosition);
            }
            else
            {
                MouseUp(boardPosition);
            }
        }
    }

    private Vector3 BoardPositionToWorldPosition(Vector2Int boardPosition)
    {
        return new Vector3(boardPosition.x, boardPosition.y, 0);
    }

    private void MouseDown(Vector2Int boardPosition)
    {

    }

    private void MouseUp(Vector2Int boardPosition)
    {
        if (Input.GetKey(KeyCode.LeftShift))
        {
            QueueCommand(boardPosition);
        }
        else
        {
            actions.Clear();
            QueueCommand(boardPosition);
        }
    }

    private void QueueCommand(Vector2Int boardPosition)
    {
        if (Input.GetKey(KeyCode.LeftControl))
        {
            List<string> newCommands = gameDisplayer.GetActionsToReachPoint(myShipUuid, boardPosition, "N");
            // TODO need to allow for choosing a direction and need to allow for starting from the end of the current actions queue
            SetAndReportActions(newCommands);
        }
        else if (Input.GetKey(KeyCode.LeftAlt))
        {
            // TODO
        }
    }

    private void SetAndReportActions(List<string> newActions)
    {
        actions = newActions;
        string actionsString = string.Join(',', newActions);
        // TODO: report actions to server
    }
}
